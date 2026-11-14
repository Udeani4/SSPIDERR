"""Small helpers shared by the blueprints."""
from functools import wraps
from urllib.parse import urlparse

from flask import g, redirect, request, url_for
from flask_login import current_user, login_required

from .services.spotify import user_client


def safe_next(target, fallback=None):
    """Only allow relative, same-site redirect targets (S3)."""
    if target:
        parsed = urlparse(target)
        if not parsed.scheme and not parsed.netloc and target.startswith("/") and not target.startswith("//"):
            return target
    return fallback


def spotify_required(view):
    """Login + a working Spotify connection. Puts the user's client in `g.sp` (A2).

    Users who haven't connected Spotify (or whose access was revoked) are sent
    to connect it and brought back afterwards.
    """
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        sp = user_client(current_user)
        if sp is None:
            return redirect(url_for("auth.connect_spotify", next=request.full_path.rstrip("?")))
        g.sp = sp
        return view(*args, **kwargs)
    return wrapper
