"""HTML scrapers for Billboard and Audiomack charts.

Parsing is split from fetching so the parsers can be tested against saved
HTML fixtures (T2). Fetches are cached because the pages are ~3 MB each.
"""
import html
import logging
import re

from bs4 import BeautifulSoup

from ..extensions import cache
from . import http

log = logging.getLogger(__name__)

BILLBOARD_URL = "https://www.billboard.com/charts/{endpoint}/"
AUDIOMACK = {
    "top_tracks": "https://audiomack.com/top/songs",
    "trending_tracks": "https://audiomack.com/trending-now/songs",
    "recent_tracks": "https://audiomack.com/recent",
    "top_albums": "https://audiomack.com/top/albums",
    "trending_albums": "https://audiomack.com/trending-now/albums",
}
VALID_CHART = re.compile(r"^[a-z0-9-]{2,60}$")


# --------------------------------------------------------------------------
# Artist-name helpers
# --------------------------------------------------------------------------
def normalise_artists(raw):
    """'A Featuring B & C' -> 'A, B, C'. Only standalone x/X/&/+ are separators (B2)."""
    s = html.unescape(raw or "").strip()
    s = re.sub(r"(?i)\s*\b(?:featuring\b|feat\.|feat\b|ft\.)\s*", ", ", s)
    s = re.sub(r"\s+(?:&|\+|x|X|with|With)\s+", ", ", s)
    s = re.sub(r"(?<=[a-z])(?=Featuring)", " ", s)     # "SnakeFeaturing" -> "Snake Featuring"
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"(,\s*){2,}", ", ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" ,")


def main_artist(full_artist):
    """First credited artist. Splits on whole words only, so 'Brandy' stays 'Brandy' (A7)."""
    if not full_artist:
        return None
    cleaned = re.sub(r"\(.*?\)", "", full_artist)
    parts = re.split(r"\s+(?:and|x|with)\s+|\s*(?:,|&|\bfeaturing\b|\bfeat\.|\bfeat\b|\bft\.)\s*",
                     cleaned, flags=re.IGNORECASE)
    first = next((p.strip() for p in parts if p.strip()), None)
    return first


# --------------------------------------------------------------------------
# Billboard
# --------------------------------------------------------------------------
def chart_type(endpoint):
    words = endpoint.split("-")
    if any(w in words for w in ("album", "albums", "200")):
        return "albums"
    if any(w in words for w in ("artist", "artists")):
        return "artists"
    return "songs"


def parse_billboard_chart(page_html, limit=10):
    """[{song, artist, main_artist}] from a Billboard chart page."""
    soup = BeautifulSoup(page_html, "html.parser")
    rows = soup.select("li.o-chart-results-list__item")
    results = []
    for row in rows:
        title_tag = row.select_one("h3")
        if not title_tag:
            continue
        artist_tag = row.select_one("span.c-label.a-no-trucate")
        name = html.unescape(title_tag.get_text(strip=True))
        artist = normalise_artists(artist_tag.get_text(strip=True)) if artist_tag else ""
        results.append({"song": name, "artist": artist, "main_artist": main_artist(artist) or ""})
        if len(results) >= limit:
            break
    return results


@cache.memoize(timeout=60 * 60 * 6)
def billboard_chart(endpoint="hot-100", chart_date=None, limit=10):
    """Fetch a chart. `chart_date` must be YYYY-MM-DD (B1). Returns (rows, type)."""
    endpoint = endpoint if endpoint and VALID_CHART.match(endpoint) else "hot-100"
    url = BILLBOARD_URL.format(endpoint=endpoint)
    if chart_date:
        url += f"{chart_date}/"
    page = http.get_text(url, browser=True, timeout=(5, 25))
    return parse_billboard_chart(page, limit), chart_type(endpoint)


def billboard_top_artists(limit=10):
    rows, _ = billboard_chart("artist-100", None, limit)
    return [r["song"] for r in rows]          # on the artist chart the h3 is the artist


# --------------------------------------------------------------------------
# Audiomack
# --------------------------------------------------------------------------
def parse_audiomack_chart(page_html, limit=10):
    """[{artist, title, main_artist}] from an Audiomack chart page."""
    soup = BeautifulSoup(page_html, "html.parser")
    out = []
    for block in soup.find_all("div", class_="ChartsItem-content"):
        data = block.find("div", class_="ChartsItem-data")
        if not data:
            continue
        artist_tag = data.find("h2", class_="ChartsItem-artist")
        title_tag = data.find("h2", class_="ChartsItem-title")
        artist = artist_tag.get_text(strip=True) if artist_tag else "Unknown Artist"
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
        out.append({"artist": artist, "title": title, "main_artist": main_artist(artist) or artist})
        if len(out) >= limit:
            break
    return out


@cache.memoize(timeout=60 * 60 * 3)
def audiomack_chart(key, limit=10):
    return parse_audiomack_chart(http.get_text(AUDIOMACK[key], browser=True, timeout=(5, 20)), limit)
