"""Shared HTTP session with timeouts, retries and connection reuse (P5).

Use `get_json()` / `get_text()` instead of calling `requests.get` directly:
every call gets a timeout, so a slow upstream can never hang a request.
"""
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = (4, 12)   # (connect, read) seconds
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def _build_session(retries=2):
    session = requests.Session()
    session.headers.update({"User-Agent": "SSPIDERR/1.0", "Accept": "application/json"})
    retry = Retry(
        total=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=40)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


HTTP = _build_session()
HTTP_FAST = _build_session(retries=0)     # for optional sources that have a fallback


def get(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT, retry=True):
    """GET with the shared session. Raises requests.RequestException on failure."""
    session = HTTP if retry else HTTP_FAST
    response = session.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response


def get_json(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT, default=None, retry=True):
    """GET a JSON document. Returns `default` (and logs) on any failure."""
    try:
        response = get(url, params=params, headers=headers, timeout=timeout, retry=retry)
        if not response.content.strip():
            return default
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("GET %s failed: %s", url.split("?")[0], describe(exc))
        return default


def describe(exc):
    """Error text without URLs, so API keys in query strings never reach the logs."""
    response = getattr(exc, "response", None)
    if response is not None:
        return f"HTTP {response.status_code}"
    return type(exc).__name__


def get_text(url, *, params=None, browser=False, timeout=DEFAULT_TIMEOUT):
    """GET an HTML page (for scrapers). Raises requests.RequestException."""
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"} if browser else None
    return get(url, params=params, headers=headers, timeout=timeout).text
