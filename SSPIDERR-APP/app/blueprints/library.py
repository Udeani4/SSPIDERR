"""The user's Spotify playlists."""
import logging

import spotipy
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import cache, limiter
from ..services import catalog
from ..services import spotify as spotify_service
from ..utils import safe_next, spotify_required

log = logging.getLogger(__name__)
bp = Blueprint("library", __name__)

PLAYLIST_CACHE_SECONDS = 300


def cached_playlists(sp, user):
    """The user's playlists, cached for 5 minutes (P2)."""
    key = f"playlists:{user.id}"
    playlists = cache.get(key)
    if playlists is None:
        playlists = spotify_service.get_user_playlists(sp, 1, me_id=user.spotify_user_id)
        cache.set(key, playlists, timeout=PLAYLIST_CACHE_SECONDS)
    return playlists


def forget_playlists(user):
    cache.delete(f"playlists:{user.id}")


@bp.route("/api/my-playlists")
def api_my_playlists():
    """Playlists for the "Add to playlist" pop-up, loaded only when it opens (P2)."""
    if not current_user.is_authenticated:
        return jsonify({"error": "Log in to add songs to a playlist.", "login": url_for("auth.login_page")}), 401
    sp = spotify_service.user_client(current_user)
    if sp is None:
        return jsonify({"error": "Connect Spotify to add songs to a playlist.",
                        "connect": url_for("auth.connect_spotify")}), 403
    try:
        playlists = cached_playlists(sp, current_user)
    except spotipy.SpotifyException as exc:
        log.warning("Listing playlists failed: %s", exc)
        return jsonify({"error": "Spotify didn't respond. Try again in a moment."}), 502
    editable = [{"id": p["id"], "name": p["name"], "image": p["image"], "tracks": p["tracks"]}
                for p in playlists if p["editable"]]
    return jsonify({"playlists": editable})


@bp.route("/add_to_playlist", methods=["POST"])
@limiter.limit("60 per minute")
def add_to_playlist():
    if not current_user.is_authenticated:
        return jsonify({"error": "Log in to add songs to a playlist."}), 401
    data = request.get_json(silent=True) or {}
    playlist_id, track_id = data.get("playlist_id"), data.get("track_id")
    if not playlist_id or not track_id:
        return jsonify({"error": "Missing playlist or song."}), 400

    sp = spotify_service.user_client(current_user)
    if sp is None:
        return jsonify({"error": "Connect Spotify first.", "connect": url_for("auth.connect_spotify")}), 403
    try:
        sp.playlist_add_items(playlist_id, [f"spotify:track:{track_id}"])
    except spotipy.SpotifyException as exc:
        log.warning("Add to playlist failed: %s", exc)
        message = ("You can only add songs to playlists you own or collaborate on."
                   if exc.http_status in (401, 403) else "Spotify couldn't add that song.")
        return jsonify({"error": message}), 502
    forget_playlists(current_user)
    return jsonify({"success": True, "message": "Song added to your playlist!"})


@bp.route("/playlist")
@spotify_required
def playlist():
    playlists = cached_playlists(g.sp, current_user)
    # Keep the local mirror in sync without making the page wait for it.
    spotify_service.start_library_sync(current_user.spotify_user_id, g.sp, playlists)
    try:
        latest = catalog.new_releases(10)
    except Exception as exc:
        log.warning("New releases failed: %s", exc)
        latest = []
    return render_template("albums-store.html", playlist_list=playlists, latest_albums=latest)


@bp.route("/playlist-page/<playlist_id>")
@spotify_required
def playlist_page(playlist_id):
    playlist = g.sp.playlist(playlist_id, fields="id,name,description,images,owner(id,display_name),external_urls")
    tracks = spotify_service.get_playlist_tracks(g.sp, playlist_id)
    stats = spotify_service.playlist_stats(tracks)
    images = playlist.get("images") or []
    image = images[0]["url"] if images else (tracks[0]["image"] if tracks else spotify_service.PLAYLIST_PLACEHOLDER)
    return render_template(
        "playlist_page.html",
        playlist1=playlist,
        playlist_tracks=tracks,
        playlist_image=image,
        avg_popularity=stats["avg_popularity"],
        total_duration=stats["total_duration_hours"],
        total_minutes=stats["total_duration_minutes"],
        is_owner=(playlist.get("owner") or {}).get("id") == current_user.spotify_user_id,
    )


@bp.route("/create-playlist", methods=["GET", "POST"])
@spotify_required
def create_playlist():
    next_page = safe_next(request.values.get("next"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Give your playlist a name.", "error")
            return render_template("create-playlist.html", next=next_page, name=name, description=description), 400
        if len(name) > 100:
            flash("Playlist names can be at most 100 characters.", "error")
            return render_template("create-playlist.html", next=next_page, name=name, description=description), 400

        existing = cached_playlists(g.sp, current_user)
        if any(p["name"].strip().lower() == name.lower() and p["editable"] for p in existing):
            flash("You already have a playlist with that name. Try a different name.", "error")
            return render_template("create-playlist.html", next=next_page, name=name, description=description), 400

        created = g.sp.user_playlist_create(user=current_user.spotify_user_id, name=name,
                                            description=description[:300])
        forget_playlists(current_user)
        flash(f"Playlist “{name}” created.", "success")
        return redirect(next_page or url_for("library.playlist_page", playlist_id=created["id"]))
    return render_template("create-playlist.html", next=next_page, name="", description="")
