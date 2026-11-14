"""Chart pages: enrich scraped chart rows with Spotify data; Grammy winners; suggestions."""
import logging
import re
from collections import Counter
from datetime import date

from bs4 import BeautifulSoup

from ..extensions import cache
from . import catalog, http, scrapers
from .concurrency import parallel_map

log = logging.getLogger(__name__)

SHORT = 250


def _short(text):
    text = re.sub(r"<[^>]+>", "", text or "").strip()
    if not text:
        return "No description currently available."
    return text[:SHORT] + "..." if len(text) > SHORT else text


def _enrich_album(row):
    match = None
    try:
        match = catalog.search_album(row["song"], row["main_artist"])
    except Exception as exc:
        log.info("album search failed: %s", exc)
    info = catalog.lastfm("album.getinfo", artist=row["main_artist"], album=row["song"])
    summary = ((info.get("album") or {}).get("wiki") or {}).get("summary")
    image = (match or {}).get("image")
    if not image:
        try:
            image = catalog.artist_image(row["main_artist"], 0)
        except Exception:
            image = None
    return {
        "album_name": row["song"],
        "album_artist": row["artist"],
        "album_main_artist": row["main_artist"],
        "spotify_album_id": (match or {}).get("id"),
        "image": image or catalog.TRACK_PLACEHOLDER,
        "description": _short(summary),
    }


def _enrich_artist(row):
    name = row["song"]          # on artist charts the h3 is the artist name
    try:
        image = catalog.artist_image(name, 0)
    except Exception:
        image = None
    try:
        description = catalog.artist_description(name)["description"]
    except Exception:
        description = None
    return {"artist_name": name, "artist_image": image or catalog.TRACK_PLACEHOLDER,
            "artist_description": _short(description)}


def _enrich_song(row):
    match = None
    try:
        match = catalog.search_track(row["song"], row["main_artist"])
    except Exception as exc:
        log.info("track search failed: %s", exc)
    preview = catalog.safe_itunes_preview(row["song"], row["main_artist"])
    image = (match or {}).get("image")
    if not image:
        try:
            image = catalog.artist_image(row["main_artist"], 1)
        except Exception:
            image = None
    return {
        "track_name": row["song"],
        "track_artist": row["artist"],
        "track_main_artist": row["main_artist"],
        "spotify_track_id": (match or {}).get("id"),
        "image": image or catalog.TRACK_PLACEHOLDER,
        "preview_url": (match or {}).get("preview_url") or preview.get("preview_url"),
    }


ENRICHERS = {"albums": _enrich_album, "artists": _enrich_artist, "songs": _enrich_song}


@cache.memoize(timeout=60 * 60 * 6)
def chart_page(endpoint="hot-100", chart_date=None, limit=10):
    """(rows, endpoint_type) ready for partials/section_results.html."""
    rows, kind = scrapers.billboard_chart(endpoint, chart_date, limit)
    enriched = parallel_map(ENRICHERS[kind], rows, max_workers=10)
    return [r for r in enriched if r], kind


def parse_chart_date(raw):
    """Accept YYYY-MM-DD (what <input type=date> sends) or MM/DD/YYYY. Returns ISO string or None."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            from datetime import datetime
            value = datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
        if value > date.today() or value.year < 1958:
            return None
        return value.isoformat()
    return None


# --------------------------------------------------------------------------
# Grammy winners (award-winning songs page)
# --------------------------------------------------------------------------
GRAMMY_URL = "https://www.grammy.com/awards/{n}{suffix}-annual-grammy-awards-{year}"
PERSON_CATEGORIES = ("best new artist", "producer of the year", "songwriter of the year")


def _ordinal_suffix(n):
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def grammy_url(ceremony_year):
    """The 67th GRAMMYs (Feb 2025) live at .../67th-annual-grammy-awards-2024 (eligibility year)."""
    n = ceremony_year - 1958
    return GRAMMY_URL.format(n=n, suffix=_ordinal_suffix(n), year=ceremony_year - 1)


def parse_grammy_winners(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    winners = []
    for item in soup.select(".accordion-item"):
        header = item.select_one(".accordion-header, .accordion-button, button")
        heading = item.select_one(".winner-heading")
        if not header or not heading:
            continue
        category = re.sub(r"\s*See all\s*$", "", header.get_text(" ", strip=True)).strip()
        title_tag = heading.find_next("p", class_="fs-xm")
        if not title_tag:
            continue
        title = title_tag.get_text(" ", strip=True)
        is_person = category.lower().startswith(PERSON_CATEGORIES)
        artist = None
        if not is_person:
            artist_tag = title_tag.find_next("p")
            artist = artist_tag.get_text(" ", strip=True) if artist_tag else None
        kind = "person" if is_person else ("album" if "album" in category.lower() else "song")
        winners.append({"category": category, "title": title, "artist": artist, "kind": kind})
    return winners


def _enrich_winner(win):
    out = dict(win, spotify_id=None, image=None, preview_url=None)
    try:
        if win["kind"] == "song":
            match = catalog.search_track(win["title"], scrapers.main_artist(win["artist"] or ""))
            if match:
                out.update(spotify_id=match["id"], image=match["image"], preview_url=match.get("preview_url"))
        elif win["kind"] == "album":
            match = catalog.search_album(win["title"], scrapers.main_artist(win["artist"] or ""))
            if match:
                out.update(spotify_id=match["id"], image=match["image"])
        else:
            out["image"] = catalog.artist_image(win["title"], 1)
    except Exception as exc:
        log.info("Grammy enrichment failed for %s: %s", win["title"], exc)
    out["image"] = out["image"] or catalog.TRACK_PLACEHOLDER
    return out


@cache.memoize(timeout=60 * 60 * 24 * 7)
def grammy_winners(ceremony_year):
    page = http.get_text(grammy_url(ceremony_year), browser=True, timeout=(5, 25))
    winners = parse_grammy_winners(page)
    return parallel_map(_enrich_winner, winners, max_workers=6)


# --------------------------------------------------------------------------
# Suggestions
# --------------------------------------------------------------------------
def _top_track_for(artist):
    data = catalog.lastfm("artist.gettoptracks", artist=artist, limit=1)
    tracks = (data.get("toptracks") or {}).get("track") or []
    if not tracks:
        return None
    row = {"song": tracks[0]["name"], "artist": artist, "main_artist": artist}
    enriched = _enrich_song(row)
    enriched["because"] = None
    return enriched


def suggestions(seed_artists, limit=12):
    """Songs by artists similar to `seed_artists` (Last.fm), excluding the seeds."""
    seeds = [a for a in seed_artists if a][:5]
    seen = {a.lower() for a in seeds}
    picks = []                      # (artist, because)
    for seed in seeds:
        try:
            similar = catalog.similar_artists(seed, 6)
        except Exception:
            similar = []
        for name in similar:
            if name.lower() not in seen:
                seen.add(name.lower())
                picks.append((name, seed))
    picks = picks[:limit]
    tracks = parallel_map(lambda p: _top_track_for(p[0]), picks, max_workers=8)
    out = []
    for (_artist, because), track in zip(picks, tracks):
        if track:
            track["because"] = because
            out.append(track)
    return out


def seed_artists_for_user(spotify_user_id, limit=5):
    """Most common artists in the user's synced library."""
    from ..models import Songs
    rows = Songs.query.with_entities(Songs.artist).filter_by(spotify_user_id=spotify_user_id).all()
    counts = Counter(scrapers.main_artist(r.artist) for r in rows if r.artist)
    return [name for name, _ in counts.most_common(limit) if name]


def global_seed_artists(limit=5):
    data = catalog.lastfm("chart.gettopartists", limit=limit)
    return [a["name"] for a in (data.get("artists") or {}).get("artist", [])][:limit]
