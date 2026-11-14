"""Music news feed and comments."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_ckeditor import CKEditorField
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import SubmitField
from wtforms.validators import DataRequired, Length

from ..extensions import db, limiter
from ..models import BlogPost, Comment
from ..services import home_feed
from ..services.sanitize import clean_html

bp = Blueprint("news", __name__)

PER_PAGE = 6


class CommentForm(FlaskForm):
    comment_text = CKEditorField("Your comment", validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField("Post comment")


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


@bp.route("/blog-post/<int:post_id>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def blog_post(post_id):
    post = db.session.scalar(db.select(BlogPost).where(BlogPost.created_id == post_id).limit(1))
    if post is None:
        abort(404)

    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("Log in or register to comment.", "info")
            return redirect(url_for("auth.login_page", next=request.path))
        text = clean_html(form.comment_text.data)     # S1: stored HTML is sanitised
        if not text.strip():
            flash("Your comment is empty.", "error")
        else:
            db.session.add(Comment(text=text, comment_author=current_user, parent_post=post))
            db.session.commit()
            flash("Comment posted.", "success")
        return redirect(url_for("news.blog_post", post_id=post_id) + "#comments")
    return render_template("blog_post.html", post=post, form=form)


@bp.route("/delete-comment/<int:comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    if comment.author_id != current_user.id:
        abort(403)
    post_created_id = comment.parent_post.created_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "info")
    return redirect(url_for("news.blog_post", post_id=post_created_id) + "#comments")
