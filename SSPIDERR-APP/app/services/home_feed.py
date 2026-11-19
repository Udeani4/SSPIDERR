"""Builds the home-page feed.

The charts on the home page are the same for every visitor, so they are built
once by the scheduler (see app/tasks.py) and stored as a single HomeData
snapshot. `home()` only ever reads the newest snapshot (A4).
"""
import logging

from flask import current_app

from ..extensions import db
from ..models import HomeData
from . import catalog, http, scrapers
from .concurrency import parallel_map, run_parallel

log = logging.getLogger(__name__)

ITUNES_RSS = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/{limit}/{kind}.json"
KEEP_SNAPSHOTS = 3
NO_DESCRIPTION = "No description available."


def _itunes_rss(kind, limit=25):
    data = http.get_json(ITUNES_RSS.format(kind=kind, limit=limit), timeout=(4, 10), retry=False)
    return ((data or {}).get("feed") or {}).get("results") or []


def top_albums(limit=10):
    rows = _itunes_rss("albums")
    if not rows:
        log.info("iTunes album RSS unavailable, using Deezer")
        return catalog.deezer_top_albums(limit)
    out = []
    for a in rows[:limit]:
        art = a.get("artworkUrl100")
        out.append({
            "album_name": a.get("name"),
            "artist_name": a.get("artistName"),
            "album_id": a.get("id"),
            "artist_id": a.get("artistId"),
            "release_date": a.get("releaseDate"),
            "genre": ((a.get("genres") or [{}])[0]).get("name", "N/A"),
            "artwork_url_original": art,
            "artwork_small": catalog.get_artwork_url(art, 100),
            "artwork_medium": catalog.get_artwork_url(art, 300),
            "artwork_full": catalog.get_artwork_url(art, 1000),
        })
    return out


def top_songs(limit=10):
    rows = _itunes_rss("songs")
    if not rows:
        log.info("iTunes song RSS unavailable, using Deezer")
        return catalog.deezer_top_songs(limit)
    return [{
        "song_name": s.get("name"),
        "song_id": s.get("id"),
        "artist_name": s.get("artistName"),
        "artwork_url_original": catalog.get_artwork_url(s.get("artworkUrl100"), 1000),
    } for s in rows[:limit]]


def top_artists(limit=10):
    try:
        artists = scrapers.billboard_top_artists(limit)
        if artists:
            return artists
    except Exception as exc:
        log.warning("Billboard artist chart failed: %s", exc)
    data = catalog.lastfm("chart.gettopartists", limit=limit)
    return [a["name"] for a in (data.get("artists") or {}).get("artist", [])][:limit]


def _global_track(item):
    name, artist = item["name"], item["artist"]
    match = None
    try:
        match = catalog.search_track(name, artist)
    except Exception as exc:
        log.info("Spotify search failed for %s: %s", name, exc)
    preview = catalog.safe_itunes_preview(name, artist)
    image = None
    try:
        image = catalog.artist_image(artist, 1)
    except Exception:
        pass
    return {
        "name": name,
        "artist": artist,
        "url": item.get("url"),
        "image": image or (match or {}).get("image"),
        "spotify_song_id": (match or {}).get("id"),
        "itunes_url": preview.get("itunes_url"),
        "preview_url": (match or {}).get("preview_url") or preview.get("preview_url"),
    }


def global_top_tracks(limit=10):
    """Last.fm global chart, enriched with Spotify ids, images and previews."""
    data = catalog.lastfm("chart.gettoptracks", limit=limit)
    items = [{"name": t["name"], "artist": t["artist"]["name"], "url": t.get("url")}
             for t in (data.get("tracks") or {}).get("track", [])[:limit]]
    return [t for t in parallel_map(_global_track, items, max_workers=10) if t]


def _artist_images(names):
    images = parallel_map(lambda n: catalog.artist_image(n, 1), names, max_workers=10)
    return {name: img for name, img in zip(names, images)}


def build_home_snapshot():
    """Fetch everything the home page shows. Raises if every source failed."""
    playlist_id = current_app.config.get("SPOTIFY_BEST_HITS_PLAYLIST_ID")
    first = run_parallel({
        "albums": (top_albums, (10,), []),
        "songs": (top_songs, (10,), []),
        "artists": (top_artists, (10,), []),
        "best_hits": (catalog.playlist_preview, (playlist_id, 15), []),
        "global": (global_top_tracks, (10,), []),
    }, max_workers=5, timeout=90)

    albums, songs, artists = first["albums"] or [], first["songs"] or [], first["artists"] or []
    if not (albums or songs or artists):
        raise RuntimeError("Every home-feed source failed")

    top_artist = artists[0] if artists else (songs[0]["artist_name"] if songs else None)
    second = run_parallel({
        "artist_images": (_artist_images, (artists,), {}),
        "artist_art": (catalog.artist_image, (top_artist, 0), None),
        "profile": (catalog.artist_profile, (top_artist,), {}),
        "description": (catalog.artist_description, (top_artist,),
                        {"source": None, "description": NO_DESCRIPTION}),
    }, max_workers=4, timeout=60)

    profile = second["profile"] or {}
    album_tracks = []
    if profile.get("album_id"):
        try:
            album_tracks = catalog.album_tracks_sorted(profile["album_id"])
        except Exception as exc:
            log.warning("Album tracks failed: %s", exc)

    top_album = albums[0] if albums else {}
    top_song = songs[0] if songs else {}
    return {
        "album_art": top_album.get("artwork_full") or top_album.get("artwork_url_original"),
        "album_name": top_album.get("album_name"),
        "album_id": str(top_album["album_id"]) if top_album.get("album_id") else None,
        "song_art": top_song.get("artwork_url_original"),
        "song_name": top_song.get("song_name"),
        "song_id": str(top_song["song_id"]) if top_song.get("song_id") else None,
        "artist_art": second["artist_art"],
        "artist_name": top_artist,
        "top_albums": albums,
        "feature_artists_info": profile,
        "artist_description": second["description"],
        "top_artist_album_track": album_tracks,
        "best_2025_hits": (first["best_hits"] or [])[:10],
        "this_weeks_hits": (first["global"] or [])[:10],
        "artist_section_dict": second["artist_images"] or {},
    }


def missing_parts(row):
    """Sections of a snapshot that came back empty (usually a rejected or missing API key).

    An incomplete snapshot is shown, but should_run_24h_task() retries it within the hour
    instead of waiting for midnight.
    """
    if row is None:
        return []                     # nothing saved yet; the normal staleness rules handle that
    missing = []
    if not row.best_2025_hits:
        missing.append("best hits (Spotify)")
    if not row.this_weeks_hits:
        missing.append("top 10 (Last.fm)")
    images = list((row.artist_section_dict or {}).values())
    if not row.artist_art or (images and not any(images)):
        missing.append("artist images (Spotify)")
    if (row.artist_description or {}).get("description", NO_DESCRIPTION) == NO_DESCRIPTION:
        missing.append("artist description (Last.fm)")
    return missing


def save_snapshot(data):
    row = HomeData(**data)
    db.session.add(row)
    db.session.commit()
    missing = missing_parts(row)
    if missing:
        log.warning("Home feed saved without: %s. Check the API keys; it will retry within the hour.",
                    ", ".join(missing))
    # Keep a few old snapshots for debugging, drop the rest (P11).
    old_ids = [r.id for r in HomeData.query.order_by(HomeData.id.desc()).offset(KEEP_SNAPSHOTS)]
    if old_ids:
        HomeData.query.filter(HomeData.id.in_(old_ids)).delete(synchronize_session=False)
        db.session.commit()
    return row


def latest_snapshot():
    return HomeData.query.order_by(HomeData.id.desc()).first()


def refresh_home_feed():
    """Job body for the scheduler: build and store a new snapshot."""
    return save_snapshot(build_home_snapshot())
