"""Public music catalogue lookups (Spotify app client, iTunes, Last.fm, Deezer).

Everything here takes plain strings and uses the app-level Spotify client, so
it is safe to call from worker threads and easy to cache (P6). Results that
change slowly are memoised; transient failures raise and are therefore *not*
cached.
"""
import logging
import re

from flask import current_app

from ..extensions import cache
from . import http
from .concurrency import parallel_map
from .spotify import TRACK_PLACEHOLDER, app_client, format_artists

log = logging.getLogger(__name__)

DAY = 60 * 60 * 24
LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"


def _q(value):
    """Strip characters that break Spotify field filters."""
    return re.sub(r'["\']', "", value or "").strip()


def get_artwork_url(original_url, size=500):
    """Resize an Apple artwork URL (they contain '100x100')."""
    if not original_url:
        return None
    return original_url.replace("100x100", f"{size}x{size}")


def _image(images, index=0, placeholder=None):
    images = images or []
    if not images:
        return placeholder
    return images[min(index, len(images) - 1)]["url"]


# --------------------------------------------------------------------------
# Spotify (public catalogue)
# --------------------------------------------------------------------------
@cache.memoize(timeout=DAY)
def search_track(title, artist=None):
    """Best Spotify match for a song, or None."""
    sp = app_client()
    queries = [f"track:{_q(title)} artist:{_q(artist)}" if artist else f"track:{_q(title)}"]
    if artist:
        queries.append(f"{_q(title)} {_q(artist)}")
    for query in queries:
        items = sp.search(q=query, type="track", limit=1)["tracks"]["items"]
        if items:
            t = items[0]
            album = t.get("album") or {}
            return {
                "id": t["id"],
                "uri": t["uri"],
                "name": t.get("name"),
                "artist": format_artists(t),
                "image": _image(album.get("images"), 0),
                "album_id": album.get("id"),
                "preview_url": t.get("preview_url"),
            }
    return None


@cache.memoize(timeout=DAY)
def search_album(title, artist=None):
    sp = app_client()
    query = f"album:{_q(title)} artist:{_q(artist)}" if artist else f"album:{_q(title)}"
    items = sp.search(q=query, type="album", limit=1)["albums"]["items"]
    if not items:
        return None
    a = items[0]
    return {
        "id": a["id"],
        "name": a.get("name"),
        "artist": ", ".join(x["name"] for x in a.get("artists", [])),
        "image": _image(a.get("images"), 0),
        "release_date": a.get("release_date"),
    }


@cache.memoize(timeout=DAY)
def search_artist(name):
    items = app_client().search(q=f"artist:{_q(name)}", type="artist", limit=1)["artists"]["items"]
    return items[0] if items else None


@cache.memoize(timeout=DAY)
def artist_image(name, index=0):
    """Artist photo: index 0 = large, 1 = medium, 2+ = small. Google image search as fallback."""
    if not name:
        return None
    artist = search_artist(name)
    if artist and artist.get("images"):
        return _image(artist["images"], index)

    return _google_image(name)


_google_disabled = False


def _google_image(name):
    """Optional fallback. Switches itself off for this process after a 4xx (bad key, quota, API shut down)."""
    global _google_disabled
    cfg = current_app.config
    if _google_disabled or not (cfg.get("GOOGLE_CLOUD_API_KEY") and cfg.get("GOOGLE_SEARCH_ENGINE_ID")):
        return None
    try:
        response = http.get("https://www.googleapis.com/customsearch/v1", params={
            "q": name, "cx": cfg["GOOGLE_SEARCH_ENGINE_ID"], "key": cfg["GOOGLE_CLOUD_API_KEY"],
            "searchType": "image", "num": 3,
        }, retry=False, timeout=(3, 8))
        items = response.json().get("items") or []
        return items[0].get("link") if items else None
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status and 400 <= status < 500:
            _google_disabled = True
            log.warning("Google image search disabled for this run (HTTP %s)", status)
        return None


@cache.memoize(timeout=DAY / 4)
def artist_profile(name):
    """Artist details plus their latest album (was `top_artist_info`). {} if not found."""
    artist = search_artist(name)
    if not artist:
        return {}
    albums = app_client().artist_albums(artist["id"], album_type="album,single", limit=20)["items"]
    albums.sort(key=lambda a: a.get("release_date") or "", reverse=True)
    latest = albums[0] if albums else None
    profile = {
        "artist_id": artist["id"],
        "artist_name": artist.get("name"),
        "genres": artist.get("genres") or [],
        "followers": (artist.get("followers") or {}).get("total"),
        "popularity": artist.get("popularity"),
        "artist_image": _image(artist.get("images"), 0),
        "spotify_link": (artist.get("external_urls") or {}).get("spotify"),
        "album_name": None, "album_id": None, "album_cover": None, "release_date": None,
    }
    if latest:
        profile.update({
            "album_name": latest.get("name"),
            "album_id": latest["id"],
            "album_cover": _image(latest.get("images"), 0),
            "release_date": latest.get("release_date"),
        })
    return profile


@cache.memoize(timeout=DAY / 4)
def album_tracks_sorted(album_id):
    """Album tracks sorted by popularity, using one batch call for popularity (P4)."""
    if not album_id:
        return []
    sp = app_client()
    album = sp.album(album_id)
    simple = (album.get("tracks") or {}).get("items") or []
    ids = [t["id"] for t in simple if t.get("id")][:50]
    full = sp.tracks(ids)["tracks"] if ids else []
    tracks = [{
        "name": t.get("name"),
        "id": t["id"],
        "popularity": t.get("popularity") or 0,
        "preview_url": t.get("preview_url"),
        "track_number": t.get("track_number"),
        "album_name": album.get("name"),
    } for t in full if t]
    tracks.sort(key=lambda t: t["popularity"], reverse=True)
    return tracks


@cache.memoize(timeout=DAY / 4)
def new_releases(limit=10):
    """Latest albums (unique by name), newest first."""
    seen, out = set(), []
    for album in app_client().new_releases(country="US", limit=30)["albums"]["items"]:
        if album["name"] in seen:
            continue
        seen.add(album["name"])
        artists = album.get("artists") or []
        out.append({
            "album_id": album["id"],
            "album_name": album["name"],
            "artist_name": ", ".join(a["name"] for a in artists),
            "main_artist": artists[0]["name"] if artists else "",
            "album_image": _image(album.get("images"), 0, TRACK_PLACEHOLDER),
            "release_date": album.get("release_date") or "",
        })
        if len(out) >= limit:
            break
    out.sort(key=lambda a: a["release_date"], reverse=True)
    return out


@cache.memoize(timeout=DAY / 4)
def playlist_preview(playlist_id, limit=15):
    """First tracks of a public playlist with iTunes preview links."""
    from .spotify import parse_playlist_track
    results = app_client().playlist_items(playlist_id, limit=limit, market="US", additional_types=("track",))
    parsed = [t for t in (parse_playlist_track(e) for e in results.get("items") or []) if t]
    # Previews are optional: one failed (or rate-limited) iTunes lookup must not empty the list.
    previews = parallel_map(lambda t: safe_itunes_preview(t["name"], t["artist"].split(" ft. ")[0]),
                            parsed, max_workers=5, default={})
    tracks = []
    for t, preview in zip(parsed, previews):
        preview = preview or {}
        tracks.append({
            "name": t["name"], "artist": t["artist"], "album": t["album"],
            "image": t["image"], "track_id": t["id"], "id": t["id"],
            "itunes_url": preview.get("itunes_url"),
            "preview_url": t["preview_url"] or preview.get("preview_url"),
            "playlist_id": playlist_id,
        })
    return tracks


# --------------------------------------------------------------------------
# iTunes
# --------------------------------------------------------------------------
@cache.memoize(timeout=DAY)
def itunes_preview(song_name, artist_name=None, country="US"):
    """iTunes match for a song: 30 s preview audio + store link. {} if none."""
    term = f"{song_name} {artist_name}" if artist_name else song_name
    data = http.get_json("https://itunes.apple.com/search", params={
        "term": term, "media": "music", "entity": "song", "limit": 1, "country": country,
    }, timeout=(3, 8), retry=False)
    if not data:
        raise RuntimeError("iTunes search failed")   # don't cache failures
    if not data.get("resultCount"):
        return {}
    song = data["results"][0]
    return {
        "track_name": song.get("trackName"),
        "artist_name": song.get("artistName"),
        "album_name": song.get("collectionName"),
        "preview_url": song.get("previewUrl"),
        "artwork_url": song.get("artworkUrl100"),
        "itunes_url": song.get("trackViewUrl"),
    }


def safe_itunes_preview(song_name, artist_name=None):
    try:
        return itunes_preview(song_name, artist_name) or {}
    except Exception:
        return {}


def itunes_lookup(item_id, entity):
    data = http.get_json("https://itunes.apple.com/lookup", params={"id": item_id, "entity": entity}, default={})
    results = (data or {}).get("results") or []
    return results[0] if results else None


def itunes_search_artist(term):
    data = http.get_json("https://itunes.apple.com/search",
                         params={"term": term, "entity": "musicArtist", "limit": 1}, default={})
    results = (data or {}).get("results") or []
    return results[0] if results else {}


# --------------------------------------------------------------------------
# Last.fm
# --------------------------------------------------------------------------
def lastfm(method, **params):
    key = current_app.config.get("LAST_FM_API_KEY")
    if not key:
        return {}
    return http.get_json(LASTFM_URL, params={"method": method, "api_key": key, "format": "json", **params},
                         default={}) or {}


@cache.memoize(timeout=DAY)
def artist_description(name):
    """{'source', 'description'} from Last.fm (iTunes no longer returns bios)."""
    data = lastfm("artist.getinfo", artist=name)
    summary = ((data.get("artist") or {}).get("bio") or {}).get("summary")
    if summary:
        return {"source": "Last.fm", "description": summary}
    return {"source": None, "description": "No description available."}


@cache.memoize(timeout=DAY)
def similar_artists(name, limit=8):
    """Replacement for Spotify's removed related-artists endpoint (A7)."""
    data = lastfm("artist.getsimilar", artist=name, limit=limit)
    return [a["name"] for a in (data.get("similarartists") or {}).get("artist", []) if a.get("name")]


# --------------------------------------------------------------------------
# Deezer (fallback when Apple's RSS feed is down)
# --------------------------------------------------------------------------
def deezer_top_albums(limit=10):
    data = http.get_json(f"https://api.deezer.com/chart/0/albums?limit={limit}", default={}) or {}
    return [{
        "album_id": a["id"],
        "artist_id": (a.get("artist") or {}).get("id"),
        "album_name": a.get("title"),
        "artist_name": (a.get("artist") or {}).get("name"),
        "genre": "N/A",
        "release_date": None,
        "artwork_url_original": a.get("cover_xl"),
        "artwork_small": a.get("cover_small"),
        "artwork_medium": a.get("cover_medium"),
        "artwork_full": a.get("cover_big"),
    } for a in data.get("data", [])[:limit]]


def deezer_top_songs(limit=10):
    data = http.get_json(f"https://api.deezer.com/chart/0/tracks?limit={limit}", default={}) or {}
    return [{
        "song_name": t.get("title"),
        "song_id": t.get("id"),
        "artist_name": (t.get("artist") or {}).get("name"),
        "artwork_url_original": (t.get("album") or {}).get("cover_xl"),
    } for t in data.get("data", [])[:limit]]
