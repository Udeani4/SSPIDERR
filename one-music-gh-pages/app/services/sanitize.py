"""HTML sanitising (S1).

Anything that is rendered without escaping (user comments, RSS summaries,
Last.fm bios) goes through `clean_html` first. It is also registered as the
`clean_html` Jinja filter so content already in the database is safe too.
"""
import hashlib

import nh3
from markupsafe import Markup

ALLOWED_TAGS = {
    "p", "br", "b", "strong", "i", "em", "u", "s", "a", "ul", "ol", "li",
    "blockquote", "h3", "h4", "code", "pre", "span",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}


def clean_html(value):
    if not value:
        return ""
    return nh3.clean(
        str(value),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )


def clean_html_filter(value):
    return Markup(clean_html(value))


def gravatar_url(email, size=100, default="retro", rating="g"):
    """Replacement for Flask-Gravatar (which is incompatible with Flask 3)."""
    digest = hashlib.md5((email or "").strip().lower().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d={default}&r={rating}"
