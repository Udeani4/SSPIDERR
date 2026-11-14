"""Music news: NewsData.io + Billboard RSS, stored as BlogPost rows.

Fetched by the scheduler (app/tasks.py), never at import time or on page
views (P9).
"""
import logging
from datetime import datetime, timezone

import feedparser
from dateutil import parser as date_parser
from flask import current_app
from sqlalchemy import func

from ..extensions import db
from ..models import BlogPost
from . import http
from .sanitize import clean_html

log = logging.getLogger(__name__)

DEFAULT_IMAGE = "/static/img/music_blog_def_image.jpeg"
BILLBOARD_FEED = "https://www.billboard.com/feed/"


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


def _article(source, title, description, content, link, raw_date, image):
    when, day, month, year = _date_parts(raw_date)
    description = clean_html(description or "")
    return {
        "source": (source or "News")[:250],
        "title": (title or "No title")[:250],
        "description": description[:250],
        "content": clean_html(content or description or "No content"),
        "link": link or "#",
        "date": when.replace(tzinfo=None),
        "image_url": (image or DEFAULT_IMAGE)[:250],
        "day": day, "month": month, "year": year,
    }


def fetch_newsdata_news():
    key = current_app.config.get("NEWS_DATA_API_KEY")
    if not key:
        return []
    data = http.get_json("https://newsdata.io/api/1/news",
                         params={"apikey": key, "q": "music", "language": "en"}, default={}) or {}
    return [
        _article(item.get("source_id") or "NewsData.io", item.get("title"), item.get("description"),
                 item.get("content") if item.get("content") and "ONLY AVAILABLE" not in str(item.get("content"))
                 else item.get("description"),
                 item.get("link"), item.get("pubDate"), item.get("image_url"))
        for item in data.get("results", []) or []
    ]


def fetch_billboard_news():
    try:
        raw = http.get_text(BILLBOARD_FEED, browser=True, timeout=(5, 20))
    except Exception as exc:
        log.warning("Billboard feed failed: %s", exc)
        return []
    articles = []
    for entry in feedparser.parse(raw).entries:
        image = None
        media = entry.get("media_content") or []
        if media:
            image = media[0].get("url")
        articles.append(_article("Billboard", entry.get("title"), entry.get("summary"), entry.get("summary"),
                                 entry.get("link"), entry.get("published"), image))
    return articles


def refresh_news():
    """Insert new articles, then keep only the newest NEWS_KEEP_LATEST. Returns #inserted."""
    articles = fetch_newsdata_news() + fetch_billboard_news()
    if not articles:
        raise RuntimeError("No news sources returned articles")

    articles.sort(key=lambda a: a["date"], reverse=True)
    next_id = (db.session.query(func.max(BlogPost.created_id)).scalar() or 0) + 1
    existing_links = {link for (link,) in db.session.query(BlogPost.news_link)}
    inserted = 0
    for art in articles:
        if art["link"] in existing_links:
            continue
        existing_links.add(art["link"])
        db.session.add(BlogPost(
            source=art["source"], title=art["title"], subtitle=art["description"], body=art["content"],
            date=art["date"], img_url=art["image_url"], created_id=next_id, news_link=art["link"],
            day=art["day"], month=art["month"], year=art["year"],
        ))
        next_id += 1
        inserted += 1
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
