"""Login, registration and the Spotify OAuth connection."""
import logging
import re
import secrets

import spotipy
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import cache, db, limiter
from ..models import User
from ..services import spotify
from ..utils import safe_next

log = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


@bp.route("/login-page", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login_page():
    next_page = safe_next(request.values.get("next"))
    if current_user.is_authenticated:
        return redirect(next_page or url_for("main.home"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = db.session.execute(db.select(User).where(db.func.lower(User.email) == email)).scalar()
        # Same message for unknown email and wrong password: don't reveal which accounts exist.
        if not user or not check_password_hash(user.password, password):
            flash("Incorrect email or password.", "error")
            return render_template("login.html", email=email, next=next_page), 401
        login_user(user, remember=bool(request.form.get("remember")))
        flash("Welcome back!", "success")
        return redirect(next_page or url_for("main.home"))

    return render_template("login.html", email="", next=next_page)


@bp.route("/register-page", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        verify = request.form.get("verify_password") or ""

        error = None
        if not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < MIN_PASSWORD:
            error = f"Your password needs at least {MIN_PASSWORD} characters."
        elif password != verify:
            error = "The passwords don't match."
        elif db.session.execute(db.select(User).where(db.func.lower(User.email) == email)).scalar():
            flash("You already have an account with that email. Log in instead.", "info")
            return redirect(url_for("auth.login_page"))
        if error:
            flash(error, "error")
            return render_template("register.html", email=email), 400

        # Werkzeug's default (scrypt) instead of pbkdf2 with an 8-char salt (S5).
        user = User(email=email, password=generate_password_hash(password))
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("You already have an account with that email. Log in instead.", "info")
            return redirect(url_for("auth.login_page"))

        login_user(user)
        flash("Account created! Connect Spotify to start building playlists.", "success")
        return redirect(url_for("auth.connect_spotify"))

    return render_template("register.html", email="")


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("main.home"))


@bp.route("/connect-spotify")
@login_required
def connect_spotify():
    """Explains why we need Spotify before sending the user to Spotify's consent page."""
    if current_user.has_spotify:
        return redirect(url_for("library.playlist"))
    return render_template("connect_spotify.html", next=safe_next(request.args.get("next")))


@bp.route("/spotify-login")
@login_required
def spotify_login():
    state = secrets.token_urlsafe(16)
    session["spotify_oauth_state"] = state
    session["spotify_next"] = safe_next(request.args.get("next"))
    return redirect(spotify.oauth_manager().get_authorize_url(state=state))


@bp.route("/callback")
@login_required
def spotify_callback():
    error = request.args.get("error")
    if error:
        flash("Spotify connection was cancelled." if error == "access_denied"
              else f"Spotify said: {error}", "error")
        return redirect(url_for("main.home"))

    state = request.args.get("state")
    if not state or state != session.pop("spotify_oauth_state", None):
        abort(400, "State mismatch. Possible CSRF or stale session.")
    code = request.args.get("code")
    if not code:
        abort(400, "Missing authorization code.")

    user = current_user._get_current_object()
    try:
        access_token = spotify.oauth_manager(user).get_access_token(code, as_dict=False, check_cache=False)
        spotify_user_id = spotipy.Spotify(auth=access_token, requests_timeout=15).me()["id"]
    except (spotipy.SpotifyException, spotipy.SpotifyOauthError) as exc:
        log.warning("Spotify callback failed: %s", exc)
        flash("We couldn't connect to Spotify. Please try again.", "error")
        return redirect(url_for("main.home"))

    other = User.query.filter(User.spotify_user_id == spotify_user_id, User.id != user.id).first()
    if other:
        spotify.clear_tokens(user)
        flash("That Spotify account is already linked to another SSPIDERR account.", "error")
        return redirect(url_for("main.home"))

    user.spotify_user_id = spotify_user_id
    db.session.commit()
    cache.delete(f"playlists:{user.id}")
    flash("Spotify connected!", "success")
    return redirect(session.pop("spotify_next", None) or url_for("library.playlist"))
