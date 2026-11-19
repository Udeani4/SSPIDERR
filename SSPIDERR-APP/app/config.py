"""Application configuration.

Every environment variable the app uses is read here, once. See `.env.example`
for the full list. Nothing else in the code base should call `os.getenv`.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# SSPIDERR-APP/  (the folder that holds app/, templates/, static/, .env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(name, default=None):
    """Read a setting, ignoring stray spaces and surrounding quotes.

    Values pasted into a hosting dashboard (e.g. Render) from .env often keep the
    quotes or a trailing space, which makes API keys silently invalid.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value if value != "" else default


def database_url(raw):
    """Use the psycopg 3 driver for PostgreSQL URLs (Render gives 'postgres://' or 'postgresql://')."""
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix):]
    return raw


def _bool(name, default=False):
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Config:
    # --- Flask core -------------------------------------------------------
    SECRET_KEY = _env("APP_SECRET_KEY")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024          # 50 MB per request (S6)
    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24        # cache static files for a day (P12)

    # --- Database ---------------------------------------------------------
    # A relative sqlite path is resolved against the instance/ folder by
    # Flask-SQLAlchemy, so this keeps using instance/my_songs.db.
    # On Render, DATABASE_URL points at the PostgreSQL database (see render.yaml).
    SQLALCHEMY_DATABASE_URI = database_url(_env("DATABASE_URL", "sqlite:///my_songs.db"))
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"connect_args": {"timeout": 15}} if SQLALCHEMY_DATABASE_URI.startswith("sqlite")
        else {"pool_pre_ping": True, "pool_recycle": 300}      # survive the database dropping idle connections
    )
    # Behind a proxy that sets X-Forwarded-* headers (Render, other hosts): set TRUST_PROXY=1.
    TRUST_PROXY = _bool("TRUST_PROXY", False)

    # --- Security ---------------------------------------------------------
    WTF_CSRF_TIME_LIMIT = None                      # token lives as long as the session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    # --- Caching (P6) -----------------------------------------------------
    CACHE_TYPE = "FileSystemCache"                  # survives restarts; CACHE_DIR set in create_app
    CACHE_DEFAULT_TIMEOUT = 60 * 60 * 6
    CACHE_THRESHOLD = 5000

    # --- Background jobs (A4 / should_run_24h_task) -----------------------
    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", True)
    # The home feed refreshes once per calendar day in this timezone (at 00:00)
    # and is never allowed to get older than HOME_REFRESH_MAX_AGE_HOURS.
    SCHEDULER_TIMEZONE = _env("SCHEDULER_TIMEZONE", "UTC")
    HOME_REFRESH_MAX_AGE_HOURS = int(_env("HOME_REFRESH_MAX_AGE_HOURS", "24"))
    NEWS_REFRESH_HOURS = int(_env("NEWS_REFRESH_HOURS", "6"))
    NEWS_KEEP_LATEST = 150

    # --- Uploads (A5) -----------------------------------------------------
    # Uploads live outside static/ so nobody can download other users' files.
    UPLOAD_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
    RECOGNITION_DELAY_SECONDS = 3                   # pause between Shazam calls
    # Per-song recognition results are kept this many days after a job finishes (0 = forever).
    UPLOAD_RESULTS_RETENTION_DAYS = int(_env("UPLOAD_RESULTS_RETENTION_DAYS", "30"))

    # --- Third-party APIs -------------------------------------------------
    SPOTIFY_CLIENT_ID = _env("SSPIDERR_SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = _env("SSPIDERR_SPOTIFY_CLIENT_SECRET")
    SPOTIFY_REDIRECT_URI = _env("SSPIDERR_SPOTIFY_REDIRECT_URI")
    SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative"
    # "Best hits" playlist shown on the home page.
    SPOTIFY_BEST_HITS_PLAYLIST_ID = _env("SPOTIFY_BEST_HITS_PLAYLIST_ID", "5iwkYfnHAGMEFLiHFFGnP4")

    LAST_FM_API_KEY = _env("LAST_FM_API_KEY")
    GOOGLE_CLOUD_API_KEY = _env("GOOGLE_CLOUD_API_KEY")
    GOOGLE_SEARCH_ENGINE_ID = _env("CX")
    NEWS_DATA_API_KEY = _env("NEWS_DATA_API_KEY")

    # --- Contact form -----------------------------------------------------
    MAIL_ADDRESS = _env("EMAIL_KEY")
    MAIL_APP_PASSWORD = _env("PASSWORD_KEY")
    CONTACT_RECIPIENT = _env("CONTACT_RECIPIENT") or _env("EMAIL_KEY")

    # --- Templates --------------------------------------------------------
    BOOTSTRAP_SERVE_LOCAL = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = "NullCache"
    SCHEDULER_ENABLED = False
    RATELIMIT_ENABLED = False
    SPOTIFY_CLIENT_ID = "test-client"
    SPOTIFY_CLIENT_SECRET = "test-secret"
    SPOTIFY_REDIRECT_URI = "http://localhost/callback"
    RECOGNITION_DELAY_SECONDS = 0


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
