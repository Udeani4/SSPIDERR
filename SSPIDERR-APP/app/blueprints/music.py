"""Song, artist, album, Afro-beats and "See what's new" pages.

All catalogue data comes from the app-level Spotify client plus iTunes,
Last.fm and Deezer, so these pages work the same for anonymous visitors and
logged-in users. The "Add to playlist" pop-up loads the user's playlists on
demand (see library.api_my_playlists), so no page waits for them.
"""
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

import spotipy
from flask import Blueprint, abort, render_template, request

from ..extensions import cache
from ..services import catalog, charts, http, scrapers
from ..services.concurrency import parallel_map, run_parallel
from ..services.spotify import TRACK_PLACEHOLDER, app_client

log = logging.getLogger(__name__)
bp = Blueprint("music", __name__)

SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")
CHART_SECTIONS = json.loads((Path(__file__).resolve().parent.parent / "data" / "chart_sections.json")
                            .read_text(encoding="utf-8"))
SECTION_IMAGES = {
    "top-charts": "img/charts/top-charts.jpg",
    "global": "img/charts/global.jpg",
    "hits-of-the-world": "img/charts/hits-of-the-world.jpg",
    "greatest-of-all-time": "img/charts/greatest-of-all-time.jpg",
    "pop": "img/charts/pop.jpg",
}


def _spotify_get(fn, *args, **kwargs):
    """Call the Spotify client; a 400/404 means 'no such item' -> 404 page."""
    try:
        return fn(*args, **kwargs)
    except spotipy.SpotifyException as exc:
        if exc.http_status in (400, 404):
            abort(404)
        raise


def _first_image(images, index=0):
    images = images or []
    return images[min(index, len(images) - 1)]["url"] if images else None


def _parse_release(value, precision="day"):
    formats = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}
    try:
        return datetime.strptime(value, formats.get(precision, "%Y-%m-%d")).date()
    except (TypeError, ValueError):
        return date.min


# --------------------------------------------------------------------------
# Song
# --------------------------------------------------------------------------
@bp.route("/song-page/<song_id>")
def song_page(song_id):
    sp = app_client()
    itunes_song = deezer = spotify_track = None
    name = artist = None

    if song_id.isdigit():                     # iTunes (or Deezer) numeric id
        found = catalog.itunes_lookup(song_id, "song")
        if found and found.get("wrapperType") == "track":
            itunes_song = found
            name, artist = found.get("trackName"), found.get("artistName")
        else:
            deezer = http.get_json(f"https://api.deezer.com/track/{song_id}", default={}) or {}
            if deezer.get("error"):
                deezer = None
            else:
                name, artist = deezer.get("title"), (deezer.get("artist") or {}).get("name")
    elif SPOTIFY_ID.match(song_id):
        spotify_track = _spotify_get(sp.track, song_id)
        name = spotify_track.get("name")
        artist = (spotify_track.get("artists") or [{}])[0].get("name")
    else:
        abort(404)

    if not name:
        abort(404)
    if spotify_track is None:                # B20: find the Spotify version by name
        match = catalog.search_track(name, artist)
        if match:
            spotify_track = sp.track(match["id"])

    extra = run_parallel({
        "lastfm": (lambda: catalog.lastfm("track.getinfo", artist=artist, track=name).get("track") or {}, (), {}),
        "preview": (catalog.safe_itunes_preview, (name, artist), {}),
        "album": (lambda aid: sp.album(aid) if aid else None,
                  ((spotify_track or {}).get("album", {}).get("id"),), None),
    })
    lastfm, preview, album = extra["lastfm"] or {}, extra["preview"] or {}, extra["album"]

    sp_album = (spotify_track or {}).get("album") or {}
    artwork = (catalog.get_artwork_url((itunes_song or {}).get("artworkUrl100"), 1000)
               or _first_image(sp_album.get("images"))
               or (deezer or {}).get("album", {}).get("cover_xl")
               or TRACK_PLACEHOLDER)
    song_data = {
        "song_name": name,
        "artist_name": artist,
        "preview_url": (itunes_song or {}).get("previewUrl") or preview.get("preview_url")
                       or (spotify_track or {}).get("preview_url"),
        "itunes": {
            "artwork": artwork,
            "release_date": (itunes_song or {}).get("releaseDate") or sp_album.get("release_date"),
            "genre": (itunes_song or {}).get("primaryGenreName"),
            "itunes_url": (itunes_song or {}).get("trackViewUrl") or preview.get("itunes_url"),
        },
        "spotify": {
            "id": (spotify_track or {}).get("id"),
            "url": ((spotify_track or {}).get("external_urls") or {}).get("spotify"),
            "popularity": (spotify_track or {}).get("popularity"),
            "duration_ms": (spotify_track or {}).get("duration_ms"),
            "release_date": sp_album.get("release_date"),
            "album": {"id": sp_album.get("id"), "name": sp_album.get("name"), "images": sp_album.get("images") or []},
            "artist_id": ((spotify_track or {}).get("artists") or [{}])[0].get("id"),
            "artist_name": artist,
        },
        "lastfm": {
            "url": lastfm.get("url"),
            "listeners": lastfm.get("listeners"),
            "playcount": lastfm.get("playcount"),
            "summary": (lastfm.get("wiki") or {}).get("summary"),
            "tags": [t["name"] for t in (lastfm.get("toptags") or {}).get("tag", [])],
        },
    }

    cover = _first_image(sp_album.get("images"), 1) or artwork
    song_album_tracks = [{
        "id": t["id"],
        "name": t.get("name"),
        "artist": ", ".join(a["name"] for a in t.get("artists", [])),
        "image": cover,
    } for t in ((album or {}).get("tracks") or {}).get("items", []) if t.get("id")]

    return render_template("song.html", song_data=song_data, song_album_tracks=song_album_tracks)


# --------------------------------------------------------------------------
# Artist
# --------------------------------------------------------------------------
def _artist_albums(artist_id):
    items = app_client().artist_albums(artist_id, album_type="album,single", limit=50)["items"]
    return list({a["id"]: a for a in items}.values())      # de-duplicate across markets


def _album_track_entries(album):
    cover = _first_image(album.get("images"), 2) or TRACK_PLACEHOLDER
    parsed = _parse_release(album.get("release_date"), album.get("release_date_precision", "day"))
    return [{
        "id": t["id"],
        "name": t.get("name"),
        "artists": ", ".join(a["name"] for a in t.get("artists", [])),
        "album_id": album["id"],
        "album_name": album.get("name"),
        "release_date": album.get("release_date"),
        "release_date_parsed": parsed,
        "release_date_iso": parsed.isoformat() if parsed != date.min else None,
        "duration_ms": t.get("duration_ms"),
        "track_image": cover,
    } for t in app_client().album_tracks(album["id"], limit=50)["items"] if t.get("id")]


@cache.memoize(timeout=60 * 60 * 3)
def artist_page_data(artist):
    spotify_artist = catalog.search_artist(artist)
    if not spotify_artist:
        return None
    artist_id, artist_name = spotify_artist["id"], spotify_artist.get("name") or artist
    sp = app_client()

    first = run_parallel({
        "top_tracks": (lambda: sp.artist_top_tracks(artist_id, country="US")["tracks"][:10], (), []),
        "albums": (_artist_albums, (artist_id,), []),
        "lastfm": (lambda: catalog.lastfm("artist.getinfo", artist=artist_name).get("artist") or {}, (), {}),
        "similar": (catalog.similar_artists, (artist_name, 8), []),
        "itunes": (catalog.itunes_search_artist, (artist_name,), {}),
    })
    albums = sorted(first["albums"] or [], key=lambda a: _parse_release(
        a.get("release_date"), a.get("release_date_precision", "day")), reverse=True)

    # P3: only fetch tracks for the newest few releases, not every album ever.
    track_lists = parallel_map(_album_track_entries, albums[:4], max_workers=4, default=[])
    seen, latest_tracks = set(), []
    for tracks in track_lists:
        for t in tracks or []:
            if t["id"] not in seen:
                seen.add(t["id"])
                latest_tracks.append(t)
    latest_tracks.sort(key=lambda t: t["release_date_parsed"], reverse=True)
    latest_tracks = latest_tracks[:10]
    for t in latest_tracks:
        t.pop("release_date_parsed", None)

    full_albums = [a for a in albums if a.get("album_type") == "album"]
    latest_album = full_albums[0] if full_albums else (albums[0] if albums else None)
    latest_album_info = []
    if latest_album:
        # Reuse the tracks fetched above when the latest album is one of the newest releases.
        fetched = {a["id"]: tracks for a, tracks in zip(albums[:4], track_lists)}
        album_tracks = fetched.get(latest_album["id"])
        if album_tracks is None:
            album_tracks = _album_track_entries(latest_album)
        latest_album_info = [{
            "track_name": t["name"], "track_id": t["id"],
            "track_artists": t["artists"], "track_image": t["track_image"],
        } for t in album_tracks or []]

    similar_names = first["similar"] or []
    similar_images = parallel_map(lambda n: catalog.artist_image(n, 1), similar_names, max_workers=8)
    related = [{"name": n, "image": img or TRACK_PLACEHOLDER} for n, img in zip(similar_names, similar_images)]

    top_tracks = first["top_tracks"] or []
    lastfm = first["lastfm"] or {}
    artist_data = {
        "artist_name": artist_name,
        "itunes": {"artist_id": (first["itunes"] or {}).get("artistId"),
                   "itunes_url": (first["itunes"] or {}).get("artistLinkUrl")},
        "spotify": {
            "id": artist_id,
            "url": (spotify_artist.get("external_urls") or {}).get("spotify"),
            "followers": (spotify_artist.get("followers") or {}).get("total"),
            "genres": spotify_artist.get("genres") or [],
            "popularity": spotify_artist.get("popularity"),
            "top_tracks": [{"id": t["id"], "name": t["name"]} for t in top_tracks],
            "latest_tracks": latest_tracks,
            "artist_art": _first_image(spotify_artist.get("images"), 0) or TRACK_PLACEHOLDER,
            "artist_latest_album": (latest_album or {}).get("name"),
            "artist_latest_album_id": (latest_album or {}).get("id"),
        },
        "lastfm": {
            "url": lastfm.get("url"),
            "listeners": (lastfm.get("stats") or {}).get("listeners"),
            "playcount": (lastfm.get("stats") or {}).get("playcount"),
            "summary": (lastfm.get("bio") or {}).get("summary"),
        },
    }
    artist_top_tracks = [{
        "track_name": t.get("name"), "track_id": t.get("id"),
        "artist_names": ", ".join(a["name"] for a in t.get("artists", [])),
        "track_image": _first_image((t.get("album") or {}).get("images"), 2) or TRACK_PLACEHOLDER,
        "preview_url": t.get("preview_url"),
    } for t in top_tracks]
    artist_albums = [{
        "name": a["name"], "id": a["id"], "release_date": a.get("release_date"),
        "total_tracks": a.get("total_tracks"), "url": (a.get("external_urls") or {}).get("spotify"),
        "image": _first_image(a.get("images"), 1) or TRACK_PLACEHOLDER,
    } for a in full_albums[:20]]
    return {
        "artist_data": artist_data, "artist_top_tracks": artist_top_tracks,
        "related_artists_data": related, "artist_albums": artist_albums,
        "artist_latest_album_info": latest_album_info,
    }


@bp.route("/artist-page/<path:artist>")
def artist_page(artist):
    data = artist_page_data(artist.strip())
    if not data:
        abort(404)
    return render_template("artist.html", **data)


# --------------------------------------------------------------------------
# Album
# --------------------------------------------------------------------------
@bp.route("/album-page/<album_id>")
def album_page(album_id):
    sp = app_client()
    itunes_album = deezer = spotify_album = None
    name = artist = None

    if album_id.isdigit():
        found = catalog.itunes_lookup(album_id, "album")
        if found and found.get("wrapperType") == "collection":
            itunes_album = found
            name, artist = found.get("collectionName"), found.get("artistName")
        else:
            deezer = http.get_json(f"https://api.deezer.com/album/{album_id}", default={}) or {}
            if deezer.get("error"):
                deezer = None
            else:
                name, artist = deezer.get("title"), (deezer.get("artist") or {}).get("name")
        if name:
            match = catalog.search_album(name, scrapers.main_artist(artist or ""))
            if match:
                spotify_album = sp.album(match["id"])
    elif SPOTIFY_ID.match(album_id):
        spotify_album = _spotify_get(sp.album, album_id)
        name = spotify_album.get("name")
        artist = (spotify_album.get("artists") or [{}])[0].get("name")
    else:
        abort(404)

    if not name:
        abort(404)

    lastfm = catalog.lastfm("album.getinfo", artist=artist, album=name).get("album") or {}
    artwork = (catalog.get_artwork_url((itunes_album or {}).get("artworkUrl100"), 1000)
               or _first_image((spotify_album or {}).get("images"))
               or (deezer or {}).get("cover_xl") or TRACK_PLACEHOLDER)
    cover_small = _first_image((spotify_album or {}).get("images"), 2) or artwork

    if spotify_album:
        raw_tracks = ((spotify_album.get("tracks") or {}).get("items") or [])
        album_tracks = [{"id": t["id"], "name": t.get("name"),
                         "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                         "image": cover_small} for t in raw_tracks if t.get("id")]
    elif deezer:
        album_tracks = [{"id": str(t["id"]), "name": t.get("title"),
                         "artist": (t.get("artist") or {}).get("name"), "image": cover_small}
                        for t in (deezer.get("tracks") or {}).get("data", [])]
    else:
        album_tracks = []

    album_data = {
        "album_name": name,
        "artist_name": artist,
        "itunes": {
            "artwork": artwork,
            "release_date": (itunes_album or {}).get("releaseDate") or (spotify_album or {}).get("release_date"),
        },
        "spotify": {
            "id": (spotify_album or {}).get("id"),
            "url": ((spotify_album or {}).get("external_urls") or {}).get("spotify"),
            "release_date": ((spotify_album or {}).get("release_date")
                             or ((itunes_album or {}).get("releaseDate") or "")[:10]
                             or (deezer or {}).get("release_date")),
            "popularity": (spotify_album or {}).get("popularity"),
            "tracks": album_tracks,
        },
        "lastfm": {
            "url": lastfm.get("url"),
            "listeners": lastfm.get("listeners"),
            "playcount": lastfm.get("playcount"),
            "summary": (lastfm.get("wiki") or {}).get("summary"),
        },
    }
    return render_template("album.html", album_data=album_data, album_tracks=album_tracks)


# --------------------------------------------------------------------------
# Afro-beats
# --------------------------------------------------------------------------
def _enrich_afro_track(row):
    match = None
    try:
        match = catalog.search_track(row["title"], row["main_artist"])
    except Exception:
        pass
    image = (match or {}).get("image")
    if not image:
        try:
            image = catalog.artist_image(row["main_artist"], 2)
        except Exception:
            image = None
    return dict(row, spotify_song_id=(match or {}).get("id"), artist_image=image or TRACK_PLACEHOLDER,
                preview_url=(match or {}).get("preview_url"))


def _enrich_afro_album(row):
    match = None
    try:
        match = catalog.search_album(row["title"], row["main_artist"])
    except Exception:
        pass
    image = (match or {}).get("image")
    if not image:
        try:
            image = catalog.artist_image(row["main_artist"], 2)
        except Exception:
            image = None
    return dict(row, spotify_album_id=(match or {}).get("id"), album_image=image or TRACK_PLACEHOLDER)


@cache.memoize(timeout=60 * 60 * 3)
def afro_page_data():
    raw = run_parallel({key: (scrapers.audiomack_chart, (key, 10), []) for key in scrapers.AUDIOMACK},
                       max_workers=5)
    track_keys = ("top_tracks", "trending_tracks", "recent_tracks")
    jobs = [(key, row) for key in scrapers.AUDIOMACK for row in (raw.get(key) or [])]
    enriched = parallel_map(
        lambda job: (_enrich_afro_track if job[0] in track_keys else _enrich_afro_album)(job[1]),
        jobs, max_workers=12)
    sections = {key: [] for key in scrapers.AUDIOMACK}
    for (key, _row), item in zip(jobs, enriched):
        if item:
            sections[key].append(item)

    top_album = next((a for a in sections["top_albums"] if a.get("spotify_album_id")), None)
    feature = {"top_afro_artist_img": None, "top_afro_album_song": [], "top_afro_artist_info": {},
               "top_afro_album": top_album}
    if top_album:
        extra = run_parallel({
            "songs": (catalog.album_tracks_sorted, (top_album["spotify_album_id"],), []),
            "image": (catalog.artist_image, (top_album["main_artist"], 0), None),
            "info": (catalog.artist_profile, (top_album["main_artist"],), {}),
        })
        feature.update(top_afro_album_song=extra["songs"] or [], top_afro_artist_img=extra["image"],
                       top_afro_artist_info=extra["info"] or {})
    return {**sections, **feature}


@bp.route("/afro-beats")
def afro_beats():
    return render_template("afro-beats.html", **afro_page_data())


# --------------------------------------------------------------------------
# See what's new (Billboard charts)
# --------------------------------------------------------------------------
@bp.route("/see-whats-new")
def see_whats_new():
    return render_template("see_whats_new.html", sections=CHART_SECTIONS, section_images=SECTION_IMAGES,
                           today=date.today().isoformat())


@bp.route("/see-whats-new-results")
def see_whats_new_results():
    endpoint = request.args.get("keyword", "hot-100")
    chart_date = charts.parse_chart_date(request.args.get("release-date"))   # B1
    try:
        rows, kind = charts.chart_page(endpoint, chart_date, 10)
        error = None if rows else "Billboard didn't return any results for that chart and date."
    except Exception as exc:
        log.warning("Chart %s/%s failed: %s", endpoint, chart_date, exc)
        rows, kind, error = [], scrapers.chart_type(endpoint), "That chart couldn't be loaded. Try another one."
    return render_template("partials/section_results.html", full_chart_info=rows, endpoint_type=kind,
                           error=error)
