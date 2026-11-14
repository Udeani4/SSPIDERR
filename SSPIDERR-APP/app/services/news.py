"""Music news: NewsData.io + Billboard RSS, stored as BlogPost rows.

Fetched by the scheduler (app/tasks.py), never at import time or on page
views (P9).
"""
import logging
import re
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from flask import current_app
from markupsafe import escape
from sqlalchemy import func

from ..extensions import db
from ..models import BlogPost
from . import http
from .concurrency import parallel_map
from .sanitize import clean_html

log = logging.getLogger(__name__)

DEFAULT_IMAGE = "/static/img/music_blog_def_image.jpeg"
BILLBOARD_FEED = "https://www.billboard.com/feed/"
EXCERPT_CHARS = 900          # we show an excerpt and link to the original, never the whole article
MAX_IMAGE_LOOKUPS = 40       # og:image fetches per refresh
OG_IMAGE = re.compile(r"""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)""", re.I)
OG_IMAGE_REVERSED = re.compile(r"""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image""", re.I)


def excerpt_html(raw_html, max_chars=EXCERPT_CHARS):
    """First paragraphs of an article (up to ~max_chars), as clean <p> tags."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paragraphs = [t for t in paragraphs if len(t) > 1]
    if not paragraphs:
        text = soup.get_text(" ", strip=True)
        paragraphs = [text] if text else []
    out, total = [], 0
    for text in paragraphs:
        if total and total + len(text) > max_chars:
            break
        if not total and len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] + "..."
        out.append(text)
        total += len(text)
    return clean_html("".join(f"<p>{escape(t)}</p>" for t in out))


def plain_summary(raw_html, limit=250):
    text = re.sub(r"\s+", " ", BeautifulSoup(raw_html or "", "html.parser").get_text(" ", strip=True))
    return text if len(text) <= limit else text[:limit - 3].rsplit(" ", 1)[0] + "..."


def og_image(url):
    """The article's share image (<meta property="og:image">), or None."""
    try:
        page = http.get_text(url, browser=True, timeout=(4, 10))
        page = page.split("</head>", 1)[0]          # the share image is always in <head>
    except Exception:
        return None
    match = OG_IMAGE.search(page) or OG_IMAGE_REVERSED.search(page)
    image = match.group(1) if match else None
    return image if image and image.startswith("https://") and len(image) <= 250 else None


def _date_parts(raw):
    """(aware datetime, day, 'Mon', year). Falls back to now when missing/invalid (B15)."""
    parsed = None
    if raw:
        try:
            parsed = date_parser.parse(raw)
        except (ValueError, OverflowError):
            parsed = None
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed, parsed.day, parsed.strftime("%b"), parsed.year


def _article(source, title, description, content, link, raw_date, image, byline=None, tags=None):
    when, day, month, year = _date_parts(raw_date)
    return {
        "source": (source or "News")[:250],
        "title": BeautifulSoup(title or "No title", "html.parser").get_text(" ", strip=True)[:250],
        "description": plain_summary(description or content),
        "content": excerpt_html(content or description) or "<p>No summary available.</p>",
        "link": link or "#",
        "date": when.replace(tzinfo=None),
        "image_url": image if image and len(image) <= 250 else None,
        "byline": (byline or "")[:200] or None,
        "tags": [t for t in (tags or []) if t][:6] or None,
        "day": day, "month": month, "year": year,
    }


def fetch_newsdata_news():
    key = current_app.config.get("NEWS_DATA_API_KEY")
    if not key:
        return []
    data = http.get_json("https://newsdata.io/api/1/news",
                         params={"apikey": key, "q": "music", "language": "en"}, default={}) or {}
    return [
        _article(item.get("source_name") or item.get("source_id") or "NewsData.io", item.get("title"),
                 item.get("description"),
                 item.get("content") if item.get("content") and "ONLY AVAILABLE" not in str(item.get("content"))
                 else item.get("description"),
                 item.get("link"), item.get("pubDate"), item.get("image_url"),
                 byline=", ".join(item.get("creator") or [])[:200] or None,
                 tags=[str(k).title() for k in (item.get("keywords") or [])])
        for item in data.get("results", []) or []
    ]


def fetch_billboard_news():
    try:
        raw = http.get_text(BILLBOARD_FEED, browser=True, timeout=(5, 20))
    except Exception as exc:
        log.warning("Billboard feed failed: %s", exc)
        return []
    articles = []
    skip_tags = {"music", "news"}
    for entry in feedparser.parse(raw).entries:
        image = None
        media = entry.get("media_content") or entry.get("media_thumbnail") or []
        if media:
            image = media[0].get("url")
        content = (entry.get("content") or [{}])[0].get("value") or entry.get("summary")
        tags = [t.term for t in entry.get("tags", []) if t.get("term") and t.term.lower() not in skip_tags
                and not t.term.lower().startswith("genre ")]
        articles.append(_article("Billboard", entry.get("title"), entry.get("summary"), content,
                                 entry.get("link"), entry.get("published"), image,
                                 byline=entry.get("author"), tags=tags))
    return articles


def refresh_news():
    """Insert new articles, then keep only the newest NEWS_KEEP_LATEST. Returns #inserted."""
    articles = fetch_newsdata_news() + fetch_billboard_news()
    if not articles:
        raise RuntimeError("No news sources returned articles")

    articles.sort(key=lambda a: a["date"], reverse=True)
    next_id = (db.session.query(func.max(BlogPost.created_id)).scalar() or 0) + 1
    existing = {p.news_link: p for p in BlogPost.query.filter(BlogPost.news_link.in_([a["link"] for a in articles]))}
    needs_image = []
    inserted = 0
    for art in articles:
        post = existing.get(art["link"])
        if post is None:
            post = BlogPost(
                source=art["source"], title=art["title"], subtitle=art["description"], body=art["content"],
                date=art["date"], img_url=art["image_url"] or DEFAULT_IMAGE, created_id=next_id,
                news_link=art["link"], byline=art["byline"], tags=art["tags"],
                day=art["day"], month=art["month"], year=art["year"],
            )
            db.session.add(post)
            existing[art["link"]] = post
            next_id += 1
            inserted += 1
        else:
            # Fill in details older rows don't have (byline, tags, a longer excerpt, a real image).
            post.byline = post.byline or art["byline"]
            post.tags = post.tags or art["tags"]
            if len(art["content"]) > len(post.body or ""):
                post.body = art["content"]
                post.subtitle = art["description"]
            if art["image_url"] and post.img_url in (None, "", DEFAULT_IMAGE):
                post.img_url = art["image_url"]
        if post.img_url in (None, "", DEFAULT_IMAGE) and art["link"].startswith("http") and post not in needs_image:
            needs_image.append(post)
    db.session.commit()

    # Billboard's feed has no images: use each article's share image instead. Older posts that
    # are no longer in the feed are filled in a few at a time on later runs.
    if len(needs_image) < MAX_IMAGE_LOOKUPS:
        needs_image += (BlogPost.query
                        .filter(BlogPost.img_url.in_((DEFAULT_IMAGE, "")), BlogPost.news_link.like("http%"),
                                BlogPost.id.not_in([p.id for p in needs_image if p.id]))
                        .order_by(BlogPost.date.desc()).limit(MAX_IMAGE_LOOKUPS - len(needs_image)).all())
    lookups = needs_image[:MAX_IMAGE_LOOKUPS]
    for post, image in zip(lookups, parallel_map(og_image, [p.news_link for p in lookups], max_workers=8)):
        if image:
            post.img_url = image
    db.session.commit()
    trim_news(current_app.config.get("NEWS_KEEP_LATEST", 150))
    return inserted


def trim_news(keep):
    keep_ids = db.select(BlogPost.id).order_by(BlogPost.date.desc()).limit(keep)
    # Never delete a post somebody has commented on.
    old = BlogPost.query.filter(BlogPost.id.not_in(keep_ids), ~BlogPost.comments.any()).all()
    for post in old:
        db.session.delete(post)
    db.session.commit()
    return len(old)
