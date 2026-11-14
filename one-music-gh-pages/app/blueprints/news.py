"""Music news feed, article pages and comments."""
import re
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from markupsafe import escape
from sqlalchemy import func
from wtforms import TextAreaField
from wtforms.validators import DataRequired, Length

from ..extensions import db, limiter
from ..models import BlogPost, Comment
from ..services import home_feed
from ..services.news import DEFAULT_IMAGE

bp = Blueprint("news", __name__)

PER_PAGE = 6
COMMENT_MIN, COMMENT_MAX = 2, 2000


class CommentForm(FlaskForm):
    comment_text = TextAreaField("Your comment", validators=[
        DataRequired("Write something first."),
        Length(COMMENT_MIN, COMMENT_MAX, f"Comments must be {COMMENT_MIN}-{COMMENT_MAX} characters."),
    ])


def comment_to_html(text):
    """Plain text from the comment box -> safe paragraphs. Blank lines start a new paragraph."""
    text = re.sub(r"\r\n?", "\n", text or "").strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join(f"<p>{escape(p)}</p>".replace("\n", "<br>") for p in paragraphs)


def comment_to_text(html):
    """Stored comment HTML -> plain text for the edit box."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", html or "")
    text = re.sub(r"(?i)</p>\s*<p[^>]*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    import html as html_lib
    return html_lib.unescape(text).strip()


@bp.route("/news-blog")
def news_blog():
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = db.paginate(db.select(BlogPost).order_by(BlogPost.date.desc()), page=page,
                             per_page=PER_PAGE, max_per_page=PER_PAGE, error_out=False)
    ids = [p.id for p in pagination.items]
    counts = dict(db.session.query(Comment.post_id, func.count(Comment.id))
                  .filter(Comment.post_id.in_(ids)).group_by(Comment.post_id).all()) if ids else {}
    comment_counts = {p.created_id: counts.get(p.id, 0) for p in pagination.items}

    snapshot = home_feed.latest_snapshot()          # sidebar "now trending" cards (B16)
    return render_template(
        "blog.html",
        news_feed=pagination.items,
        page=pagination.page,
        total_pages=max(pagination.pages, 1),
        comment_counts=comment_counts,
        album_name=getattr(snapshot, "album_name", None),
        album_id=getattr(snapshot, "album_id", None),
        album_art=getattr(snapshot, "album_art", None),
        song_name=getattr(snapshot, "song_name", None),
        song_id=getattr(snapshot, "song_id", None),
        song_art=getattr(snapshot, "song_art", None),
    )


def _related_posts(post, limit=4):
    """Posts sharing a tag first, then the latest ones from anywhere."""
    recent = (BlogPost.query.filter(BlogPost.id != post.id).order_by(BlogPost.date.desc()).limit(60).all())
    tags = {t.lower() for t in (post.tags or [])}
    scored = sorted(recent, key=lambda p: (-len(tags & {t.lower() for t in (p.tags or [])}),
                                           p.img_url in (None, "", DEFAULT_IMAGE)))
    return scored[:limit]


def _render_post(post, form, status=200):
    sort = "newest" if request.args.get("sort") == "newest" else "oldest"
    comments = sorted(post.comments, key=lambda c: c.created_at, reverse=(sort == "newest"))
    newer = (BlogPost.query.filter(BlogPost.date > post.date).order_by(BlogPost.date.asc()).first())
    older = (BlogPost.query.filter(BlogPost.date < post.date).order_by(BlogPost.date.desc()).first())
    return render_template(
        "blog_post.html", post=post, form=form, comments=comments, sort=sort,
        related=_related_posts(post), newer=newer, older=older,
        has_image=post.img_url not in (None, "", DEFAULT_IMAGE),
        comment_max=COMMENT_MAX,
    ), status


@bp.route("/blog-post/<int:post_id>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def blog_post(post_id):
    post = db.session.scalar(db.select(BlogPost).where(BlogPost.created_id == post_id).limit(1))
    if post is None:
        abort(404)

    form = CommentForm()
    if request.method == "POST":
        if not current_user.is_authenticated:
            flash("Log in or create an account to comment.", "info")
            return redirect(url_for("auth.login_page", next=url_for("news.blog_post", post_id=post_id) + "#comments"))
        if not form.validate_on_submit():
            for errors in form.errors.values():
                for message in errors:
                    flash(message, "error")
            return _render_post(post, form, 400)
        comment = Comment(text=comment_to_html(form.comment_text.data), comment_author=current_user, parent_post=post)
        db.session.add(comment)
        db.session.commit()
        flash("Your comment is live.", "success")
        return redirect(url_for("news.blog_post", post_id=post_id) + f"#comment-{comment.id}")
    return _render_post(post, form)


def _own_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    if comment.author_id != current_user.id:
        abort(403)
    return comment


@bp.route("/comments/<int:comment_id>/edit", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def edit_comment(comment_id):
    comment = _own_comment(comment_id)
    text = (request.form.get("comment_text") or "").strip()
    if not COMMENT_MIN <= len(text) <= COMMENT_MAX:
        flash(f"Comments must be {COMMENT_MIN}-{COMMENT_MAX} characters.", "error")
    else:
        comment.text = comment_to_html(text)
        comment.edited_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        flash("Comment updated.", "success")
    return redirect(url_for("news.blog_post", post_id=comment.parent_post.created_id) + f"#comment-{comment.id}")


@bp.route("/delete-comment/<int:comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = _own_comment(comment_id)
    post_created_id = comment.parent_post.created_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "info")
    return redirect(url_for("news.blog_post", post_id=post_created_id) + "#comments")


@bp.app_template_filter("comment_text")
def comment_text_filter(html):
    return comment_to_text(html)
