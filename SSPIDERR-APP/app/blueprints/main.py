"""Home, about, contact and the chart landing pages."""
import logging
import smtplib
from datetime import date
from email.mime.text import MIMEText

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import tasks
from ..extensions import db, limiter
from ..models import ReviewComment
from ..services import charts, home_feed

log = logging.getLogger(__name__)
bp = Blueprint("main", __name__)

ABOUT_PAGES = {
    "overview": "about_overview.html",
    "discover": "about_discover.html",
    "new_releases": "about_new_releases.html",
    "newsroom": "about_newsroom.html",
    "local_spotify": "about_local_spotify.html",
    "playlist_hub": "about_playlist_hub.html",
}

EMPTY_FEED = {
    "album_art": None, "album_name": None, "album_id": None,
    "song_art": None, "song_name": None, "song_id": None,
    "artist_art": None, "artist_name": None,
    "top_albums": [], "feature_artists_info": {}, "artist_description": {},
    "top_artist_album_track": [], "best_2025_hits": [], "this_weeks_hits": [], "artist_section_dict": {},
}


def _feed_context(snapshot):
    if snapshot is None:
        return dict(EMPTY_FEED)
    ctx = {key: getattr(snapshot, key) for key in EMPTY_FEED}
    for key, default in EMPTY_FEED.items():
        if ctx[key] is None:
            ctx[key] = default
    ctx["feed_updated_at"] = snapshot.created_at
    return ctx


@bp.route("/", methods=["GET"])
def home():
    snapshot = home_feed.latest_snapshot()
    if snapshot is None:
        # First run ever: build the feed now so the page isn't empty.
        tasks.run_job(tasks.HOME_JOB, force=True)
        snapshot = home_feed.latest_snapshot()
    elif tasks.should_run_24h_task(tasks.HOME_JOB):
        # Stale: show what we have instantly and refresh in the background.
        tasks.run_job_in_background(tasks.HOME_JOB)
    return render_template("index.html", **_feed_context(snapshot))


@bp.route("/status/jobs")
@login_required
def jobs_status():
    """Health check for the background jobs (also handy when debugging)."""
    return jsonify({
        "home_feed": dict(tasks.job_status(tasks.HOME_JOB), due=tasks.should_run_24h_task(tasks.HOME_JOB)),
        "news_feed": dict(tasks.job_status(tasks.NEWS_JOB), due=tasks.should_run_24h_task(tasks.NEWS_JOB)),
    })


@bp.route("/about-us", defaults={"name": None}, methods=["GET", "POST"])
@bp.route("/about-us/<name>", methods=["GET"])
def about_us(name):
    if request.method == "POST":
        if not current_user.is_authenticated:
            flash("Log in to leave a review.", "info")
            return redirect(url_for("auth.login_page", next=url_for("main.about_us")))
        text = (request.form.get("review") or request.form.get("search") or "").strip()
        if not text:
            flash("Your review is empty.", "error")
        elif len(text) > 1000:
            flash("Please keep reviews under 1000 characters.", "error")
        else:
            db.session.add(ReviewComment(text=text, author_id=current_user.id))
            db.session.commit()
            flash("Thanks! Your review has been saved.", "success")
        return redirect(url_for("main.about_us") + "#reviews")

    if name is None:
        reviews = ReviewComment.query.order_by(ReviewComment.created_at.desc()).limit(50).all()
        return render_template("event.html", sorted_data=reviews)
    if name in ABOUT_PAGES:
        return render_template(ABOUT_PAGES[name])
    return redirect(url_for("main.about_us"))


def send_email(name, email, subject, message):
    cfg = current_app.config
    if not (cfg.get("MAIL_ADDRESS") and cfg.get("MAIL_APP_PASSWORD") and cfg.get("CONTACT_RECIPIENT")):
        raise RuntimeError("Email is not configured")
    msg = MIMEText(f"{message}\n\n\nSender: {name} <{email}>", "plain", "utf-8")
    msg["From"] = cfg["MAIL_ADDRESS"]
    msg["To"] = cfg["CONTACT_RECIPIENT"]
    msg["Reply-To"] = email
    msg["Subject"] = f"***SSPIDERR*** {name}: {subject}"
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as connection:
        connection.login(cfg["MAIL_ADDRESS"], cfg["MAIL_APP_PASSWORD"])
        connection.sendmail(cfg["MAIL_ADDRESS"], [cfg["CONTACT_RECIPIENT"]], msg.as_string())


@bp.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def contact():
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in ("name", "email", "subject", "message")}
        if not form["name"] or "@" not in form["email"] or not form["message"]:
            flash("Please fill in your name, a valid email and a message.", "error")
            return render_template("contact.html", form=form), 400
        try:
            send_email(form["name"], form["email"], form["subject"] or "(no subject)", form["message"][:5000])
        except (smtplib.SMTPException, OSError, RuntimeError) as exc:
            log.error("Contact email failed: %s", exc)
            flash("Sorry, your message couldn't be sent right now. Please try again later.", "error")
            return render_template("contact.html", form=form), 503
        flash("Message sent! Thank you for the feedback.", "success")
        return redirect(url_for("main.contact"))
    return render_template("contact.html", form={})


# --------------------------------------------------------------------------
# Chart landing pages linked from the home page
# --------------------------------------------------------------------------
def _chart(endpoint, chart_date=None, limit=10):
    try:
        return charts.chart_page(endpoint, chart_date, limit)
    except Exception as exc:
        log.warning("Chart %s %s failed: %s", endpoint, chart_date, exc)
        return [], "songs"


@bp.route("/US-top-40-songs")
def US_top_40_songs():
    rows, kind = _chart("hot-100", None, 40)
    return render_template("chart_page.html", title="US Top 40", subtitle="Billboard Hot 100, this week",
                           full_chart_info=rows, endpoint_type=kind)


@bp.route("/top-hits-time-travel")
def time_travel_hits():
    chart_date = charts.parse_chart_date(request.args.get("date"))
    rows, kind = _chart("hot-100", chart_date, 20) if chart_date else ([], "songs")
    if request.args.get("date") and not chart_date:
        flash("Pick a date between 1958 and today.", "error")
    return render_template("time_travel.html", chart_date=chart_date, full_chart_info=rows, endpoint_type=kind,
                           today=date.today().isoformat())


@bp.route("/suggested-songs")
def AI_suggested_songs():
    seeds, personal = [], False
    if current_user.is_authenticated and current_user.spotify_user_id:
        seeds = charts.seed_artists_for_user(current_user.spotify_user_id)
        personal = bool(seeds)
    if not seeds:
        seeds = charts.global_seed_artists()
    try:
        picks = charts.suggestions(seeds)
    except Exception as exc:
        log.warning("Suggestions failed: %s", exc)
        picks = []
    return render_template("suggestions.html", picks=picks, seeds=seeds, personal=personal)


@bp.route("/award-winning-songs")
def award_winning_songs():
    latest = date.today().year if date.today().month >= 3 else date.today().year - 1
    year = request.args.get("year", type=int) or latest
    if year < 2000 or year > latest:
        abort(404)
    try:
        winners = charts.grammy_winners(year)
    except Exception as exc:
        log.warning("Grammy winners %s failed: %s", year, exc)
        winners = []
    return render_template("award_winning_songs.html", winners=winners, year=year,
                           years=list(range(latest, 2009, -1)))
