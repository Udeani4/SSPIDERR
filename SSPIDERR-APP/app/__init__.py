"""SSPIDERR application factory."""
import logging
import os
from pathlib import Path

import spotipy
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import event

from .config import BASE_DIR, CONFIGS, database_url
from .extensions import bootstrap, cache, csrf, db, limiter, login_manager, migrate


def _configure_logging(app):
    level = logging.DEBUG if app.debug and os.environ.get("LOG_LEVEL") == "DEBUG" else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    for noisy in ("spotipy", "apscheduler.executors", "shazamio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.ERROR)        # retries are logged by app.services.http


def _enable_sqlite_wal(app):
    """WAL lets background threads write while requests read (P11)."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite") or ":memory:" in app.config[
            "SQLALCHEMY_DATABASE_URI"]:
        return
    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def _pragma(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()


def create_app(config_name=None, instance_path=None, **overrides):
    config_name = config_name or os.environ.get("APP_ENV") or (
        "development" if os.environ.get("FLASK_DEBUG") == "1" else "production")
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
        instance_path=str(instance_path or BASE_DIR / "instance"),
    )
    app.config.from_object(CONFIGS[config_name])
    app.config.update(overrides)
    uri = app.config["SQLALCHEMY_DATABASE_URI"] = database_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if not uri.startswith("sqlite") and "connect_args" in app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}
    if app.config.get("TRUST_PROXY"):
        # Render terminates HTTPS in front of the app; trust its X-Forwarded-* headers so
        # request.url, url_for(_external=True) and client IPs (rate limits) are correct.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("APP_SECRET_KEY is not set. Copy .env.example to .env and fill it in.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.setdefault("CACHE_DIR", str(Path(app.instance_path) / "cache"))
    _configure_logging(app)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    bootstrap.init_app(app)
    _enable_sqlite_wal(app)

    from .services import spotify
    spotify.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        # Returning None (not 404) logs out cookies for deleted users (B11).
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # Jinja helpers
    from .services.sanitize import clean_html_filter, gravatar_url
    app.jinja_env.filters["clean_html"] = clean_html_filter
    app.jinja_env.filters["gravatar"] = gravatar_url

    @app.context_processor
    def inject_globals():
        from datetime import date
        return {"now_year": date.today().year}

    @app.template_filter("timeago")
    def timeago(value):
        """'3 hours ago'. Stored datetimes are naive UTC."""
        from datetime import datetime, timezone
        if not value:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        seconds = int((datetime.now(timezone.utc) - value).total_seconds())
        if seconds < 60:
            return "just now"
        for unit, size in (("year", 31_536_000), ("month", 2_592_000), ("week", 604_800),
                           ("day", 86_400), ("hour", 3_600), ("minute", 60)):
            if seconds >= size:
                n = seconds // size
                return f"{n} {unit}{'s' if n != 1 else ''} ago"
        return "just now"

    @app.template_filter("reading_time")
    def reading_time(html):
        import re
        words = len(re.sub(r"<[^>]+>", " ", html or "").split())
        return max(1, round(words / 220))

    @app.template_filter("thousands")
    def thousands(value):
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return value if value not in (None, "") else "-"

    # Blueprints
    from .blueprints import auth, library, main, music, news, uploads
    for bp in (main.bp, auth.bp, music.bp, library.bp, news.bp, uploads.bp):
        app.register_blueprint(bp)

    _register_error_handlers(app)
    _register_startup(app)
    return app


def _register_error_handlers(app):
    def wants_json():
        return request.path.startswith(("/api/", "/jobs", "/add_to_playlist")) or request.is_json

    def render_error(code, title, message):
        if wants_json():
            return jsonify({"error": message}), code
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(404)
    def not_found(_e):
        return render_error(404, "Page not found", "We couldn't find that page, song or artist.")

    @app.errorhandler(403)
    def forbidden(_e):
        return render_error(403, "Not allowed", "You don't have permission to do that.")

    @app.errorhandler(413)
    def too_large(_e):
        return render_error(413, "File too large", "That file is bigger than the 50 MB limit.")

    @app.errorhandler(429)
    def too_many(_e):
        return render_error(429, "Slow down", "Too many attempts. Please wait a minute and try again.")

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_error(400, "Session expired", "Your session expired. Refresh the page and try again.")

    @app.errorhandler(spotipy.SpotifyOauthError)
    def spotify_credentials_error(e):
        # The app's own Client ID/Secret were refused (not a user's account problem).
        app.logger.error(
            "Spotify rejected SSPIDERR's app credentials (%s). Check SSPIDERR_SPOTIFY_CLIENT_ID and "
            "SSPIDERR_SPOTIFY_CLIENT_SECRET: they must match the Spotify Developer Dashboard exactly, "
            "with no quotes or spaces.", getattr(e, "error", None) or e)
        return render_error(503, "Spotify is unavailable right now",
                            "We can't reach Spotify at the moment. Charts and news still work; "
                            "please try this page again later.")

    @app.errorhandler(spotipy.SpotifyException)
    def spotify_error(e):
        from flask_login import current_user

        from .services import spotify as spotify_service
        if spotify_service.is_not_registered(e):
            # Removed from (or never on) the Development Mode user list: disconnect so they aren't stuck.
            if current_user.is_authenticated and current_user.has_spotify:
                spotify_service.clear_tokens(current_user._get_current_object())
            return render_error(403, "Spotify access is invite-only", spotify_service.INVITE_ONLY_MESSAGE)
        app.logger.warning("Unhandled Spotify error on %s: %s", request.path, e)
        if getattr(e, "http_status", None) == 404:
            return render_error(404, "Not found on Spotify", "Spotify doesn't have that item.")
        return render_error(502, "Spotify is having trouble",
                            "Spotify didn't respond properly. Please try again in a moment.")

    @app.errorhandler(500)
    def server_error(_e):
        return render_error(500, "Something went wrong", "An unexpected error happened. Please try again.")


def _register_startup(app):
    from . import tasks
    from .services import uploads

    if not app.testing:
        tasks.clear_stale_locks(app)
        uploads.recover_interrupted_jobs(app)

    started = {"done": False}

    @app.before_request
    def _start_background_jobs():
        if not started["done"]:
            started["done"] = True
            tasks.start_scheduler(app)
