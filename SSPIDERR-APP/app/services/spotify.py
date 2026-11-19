"""Spotify clients, token handling and the user's library.

Two kinds of client:

* `app_client()`  - client-credentials client for public catalogue data
  (search, artists, albums). Safe to use from any thread.
* `user_client(user)` - acts as the logged-in user (playlists). Must be
  created in the request thread because refreshing the token writes to the DB.
  Pass the resulting client (or plain ids) into worker threads, never
  `current_user` (A3).
"""
import logging
import threading
import time

import requests
import spotipy
from flask import current_app, has_request_context
from flask_login import current_user
from spotipy.cache_handler import CacheHandler, MemoryCacheHandler
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth, SpotifyOauthError

from ..extensions import db

log = logging.getLogger(__name__)

INVITE_ONLY_MESSAGE = (
    "Spotify connection is invite-only for now. SSPIDERR runs in Spotify's Development Mode, which only lets "
    "a few approved Spotify accounts connect. Ask the site owner to add the email address of your Spotify account."
)


def is_not_registered(exc):
    """True when Spotify refuses a user because they aren't on the app's Development Mode user list.

    Spotify answers HTTP 403 with a message like "...the user may not be registered".
    """
    if getattr(exc, "http_status", None) != 403:
        return False
    text = f"{getattr(exc, 'msg', '')} {exc}".lower()
    return "not be registered" in text or "not registered" in text


PLAYLIST_PLACEHOLDER = "/static/img/core-img/playlist-placeholder.svg"
TRACK_PLACEHOLDER = "/static/img/core-img/track-placeholder.svg"

_credentials = {}
_app_client = None
_app_client_lock = threading.Lock()


def init_app(app):
    """Remember API credentials so worker threads don't need an app context."""
    _credentials.update(
        client_id=app.config.get("SPOTIFY_CLIENT_ID"),
        client_secret=app.config.get("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=app.config.get("SPOTIFY_REDIRECT_URI"),
        scope=app.config.get("SPOTIFY_SCOPE"),
    )


# --------------------------------------------------------------------------
# Token storage
# --------------------------------------------------------------------------
class DBTokenCache(CacheHandler):
    """Stores a user's Spotify tokens on the User row (replaces classes.py)."""

    def __init__(self, user):
        self.user = user

    def get_cached_token(self):
        user = self.user
        if not user or not user.spotify_ref_tok:
            return None
        return {
            "access_token": user.spotify_acc_tok,
            "refresh_token": user.spotify_ref_tok,
            "expires_at": user.spotify_token_expires_at or 0,
            "scope": _credentials.get("scope"),
            "token_type": "Bearer",
        }

    def save_token_to_cache(self, token_info):
        user = self.user
        user.spotify_acc_tok = token_info["access_token"]
        # Spotify only sometimes rotates the refresh token; keep the old one otherwise.
        if token_info.get("refresh_token"):
            user.spotify_ref_tok = token_info["refresh_token"]
        if token_info.get("expires_at"):
            user.spotify_token_expires_at = int(token_info["expires_at"])
        db.session.commit()


def oauth_manager(user=None):
    return SpotifyOAuth(
        client_id=_credentials.get("client_id"),
        client_secret=_credentials.get("client_secret"),
        redirect_uri=_credentials.get("redirect_uri"),
        scope=_credentials.get("scope"),
        cache_handler=DBTokenCache(user) if user is not None else MemoryCacheHandler(),
        open_browser=False,
        requests_timeout=15,
    )


def clear_tokens(user):
    user.spotify_acc_tok = None
    user.spotify_ref_tok = None
    user.spotify_token_expires_at = None
    db.session.commit()


def get_valid_access_token(user):
    """Return a usable access token for `user`, refreshing only when needed (B12).

    Returns None if the user never connected Spotify, or if Spotify revoked
    the refresh token (the tokens are then cleared so the UI asks to reconnect).
    """
    if user is None or not getattr(user, "is_authenticated", False) or not user.spotify_ref_tok:
        return None

    now = int(time.time())
    if user.spotify_acc_tok and user.spotify_token_expires_at and user.spotify_token_expires_at - 60 > now:
        return user.spotify_acc_tok

    try:
        token_info = oauth_manager(user).refresh_access_token(user.spotify_ref_tok)  # saves via DBTokenCache
        return token_info["access_token"]
    except SpotifyOauthError as exc:
        # invalid_grant: the user revoked access or the token is otherwise dead.
        log.warning("Spotify refresh rejected for user %s: %s", user.id, exc)
        clear_tokens(user)
        return None
    except (requests.RequestException, spotipy.SpotifyException) as exc:
        log.warning("Spotify refresh failed for user %s: %s", user.id, exc)
        return None


def user_client(user=None):
    """Spotify client acting as `user` (default: current_user), or None."""
    if user is None and has_request_context():
        user = current_user
    token = get_valid_access_token(user)
    if not token:
        return None
    return spotipy.Spotify(auth=token, requests_timeout=15, retries=2, status_retries=2)


def app_client():
    """Client-credentials client for public catalogue data. Thread-safe."""
    global _app_client
    with _app_client_lock:
        if _app_client is None:
            manager = SpotifyClientCredentials(
                client_id=_credentials.get("client_id"),
                client_secret=_credentials.get("client_secret"),
                requests_timeout=15,
                cache_handler=MemoryCacheHandler(),   # don't write a .cache token file to disk
            )
            _app_client = spotipy.Spotify(
                client_credentials_manager=manager, requests_timeout=15, retries=2, status_retries=2)
        return _app_client


def client_for_request():
    """(client, source): the user's client if they connected Spotify, else the app client."""
    sp = user_client() if has_request_context() else None
    if sp is not None:
        return sp, "user"
    return app_client(), "app"


# --------------------------------------------------------------------------
# Playlists
# --------------------------------------------------------------------------
def _pick_image(images, index=1, placeholder=PLAYLIST_PLACEHOLDER):
    images = images or []
    if not images:
        return placeholder
    return images[min(index, len(images) - 1)]["url"]


def _track_total(item):
    # Spotify has been renaming "tracks" to "items" on playlist objects.
    block = item.get("tracks") or item.get("items") or {}
    return block.get("total", 0) if isinstance(block, dict) else 0


def get_user_playlists(sp, image_index=1, me_id=None):
    """All of the user's playlists from the listing endpoint only (P1).

    One request per 50 playlists - no per-playlist calls. `me_id` (the user's
    Spotify id) marks which playlists the user can add songs to.
    """
    if sp is None:
        return []
    if me_id is None:
        try:
            me_id = sp.me()["id"]
        except spotipy.SpotifyException:
            me_id = None

    playlists = []
    results = sp.current_user_playlists(limit=50)
    while results:
        for item in results.get("items") or []:
            if not item:
                continue
            owner = item.get("owner") or {}
            total = _track_total(item)
            playlists.append({
                "id": item["id"],
                "name": item.get("name") or "Untitled playlist",
                "owner": owner.get("display_name") or owner.get("id"),
                "owner_id": owner.get("id"),
                "editable": owner.get("id") == me_id or bool(item.get("collaborative")),
                "tracks": total,
                "num_tracks": total,
                "image": _pick_image(item.get("images"), image_index),
                "description": item.get("description") or "",
                "public": item.get("public"),
                "snapshot_id": item.get("snapshot_id"),
            })
        results = sp.next(results) if results.get("next") else None
    return playlists


def format_artists(track):
    """'Main Artist ft. Others'."""
    names = [a.get("name") for a in track.get("artists") or [] if a.get("name")]
    if not names:
        return "Unknown artist"
    if len(names) == 1:
        return names[0]
    return f"{names[0]} ft. {', '.join(names[1:])}"


def parse_playlist_track(entry):
    """Normalise one playlist_items entry. Returns None for removed/local items."""
    track = entry.get("item") or entry.get("track")
    if not track or not track.get("id") or track.get("type", "track") != "track":
        return None
    album = track.get("album") or {}
    return {
        "id": track["id"],
        "name": track.get("name") or "Unknown",
        "album": album.get("name") or "",
        "image": _pick_image(album.get("images"), 0, TRACK_PLACEHOLDER),
        "artist": format_artists(track),
        "duration_ms": track.get("duration_ms") or 0,
        "popularity": track.get("popularity") or 0,
        "preview_url": track.get("preview_url"),
        "external_url": (track.get("external_urls") or {}).get("spotify", ""),
        "uri": track.get("uri"),
    }


def get_playlist_tracks(sp, playlist_id, limit=None):
    """All tracks of a playlist (paginated), skipping local files/episodes (B4)."""
    tracks = []
    results = sp.playlist_items(playlist_id, limit=100, additional_types=("track",))
    while results:
        for entry in results.get("items") or []:
            parsed = parse_playlist_track(entry)
            if parsed:
                tracks.append(parsed)
                if limit and len(tracks) >= limit:
                    return tracks
        results = sp.next(results) if results.get("next") else None
    return tracks


def playlist_stats(tracks):
    """Average popularity and total duration, computed from the tracks we already have."""
    if not tracks:
        return {"avg_popularity": 0, "total_duration_hours": 0, "total_duration_minutes": 0}
    total_ms = sum(t["duration_ms"] for t in tracks)
    return {
        "avg_popularity": round(sum(t["popularity"] for t in tracks) / len(tracks)),
        "total_duration_hours": total_ms // 3_600_000,
        "total_duration_minutes": (total_ms // 60_000) % 60,
    }


def sync_user_library(app, spotify_user_id, sp, playlists):
    """Mirror the user's playlists into the DB, re-downloading only changed ones (P11).

    Runs in a background thread: takes plain values, opens its own app context.
    """
    from ..models import Playlist, Songs

    with app.app_context():
        try:
            existing = {p.spotify_playlist_id: p for p in
                        Playlist.query.filter_by(spotify_user_id=spotify_user_id)}
            seen = set()
            for pl in playlists:
                seen.add(pl["id"])
                row = existing.get(pl["id"])
                if row and row.snapshot_id and row.snapshot_id == pl.get("snapshot_id"):
                    row.name, row.description = pl["name"], pl["description"]
                    continue
                if row is None:
                    row = Playlist(spotify_playlist_id=pl["id"], spotify_user_id=spotify_user_id)
                    db.session.add(row)
                row.name, row.description, row.snapshot_id = pl["name"][:100], pl["description"], pl.get("snapshot_id")

                Songs.query.filter_by(spotify_user_id=spotify_user_id, spotify_playlist_id=pl["id"]).delete()
                for t in get_playlist_tracks(sp, pl["id"]):
                    db.session.add(Songs(
                        track_id=t["id"], name=t["name"][:100], album=t["album"][:100], artist=t["artist"][:100],
                        duration_ms=t["duration_ms"], popularity=t["popularity"], preview_url=t["preview_url"],
                        external_url=t["external_url"], spotify_playlist_id=pl["id"],
                        spotify_user_id=spotify_user_id,
                    ))
                db.session.commit()

            for pid, row in existing.items():
                if pid not in seen:
                    Songs.query.filter_by(spotify_user_id=spotify_user_id, spotify_playlist_id=pid).delete()
                    db.session.delete(row)
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("Library sync failed for %s", spotify_user_id)


def start_library_sync(spotify_user_id, sp, playlists):
    app = current_app._get_current_object()
    threading.Thread(
        target=sync_user_library, args=(app, spotify_user_id, sp, playlists),
        name=f"library-sync-{spotify_user_id}", daemon=True,
    ).start()
