"""Application configuration.

Every environment variable the app uses is read here, once. See `.env.example`
for the full list. Nothing else in the code base should call `os.getenv`.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# one-music-gh-pages/  (the folder that holds app/, templates/, static/, .env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- Flask core -------------------------------------------------------
    SECRET_KEY = os.environ.get("APP_SECRET_KEY")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024          # 50 MB per request (S6)
    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24        # cache static files for a day (P12)

    # --- Database ---------------------------------------------------------
    # A relative sqlite path is resolved against the instance/ folder by
    # Flask-SQLAlchemy, so this keeps using instance/my_songs.db.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///my_songs.db")
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15}}

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
    SCHEDULER_TIMEZONE = os.environ.get("SCHEDULER_TIMEZONE", "UTC")
    HOME_REFRESH_MAX_AGE_HOURS = int(os.environ.get("HOME_REFRESH_MAX_AGE_HOURS", "24"))
    NEWS_REFRESH_HOURS = int(os.environ.get("NEWS_REFRESH_HOURS", "6"))
    NEWS_KEEP_LATEST = 150

    # --- Uploads (A5) -----------------------------------------------------
    # Uploads live outside static/ so nobody can download other users' files.
    UPLOAD_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
    RECOGNITION_DELAY_SECONDS = 3                   # pause between Shazam calls

    # --- Third-party APIs -------------------------------------------------
    SPOTIFY_CLIENT_ID = os.environ.get("SSPIDERR_SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.environ.get("SSPIDERR_SPOTIFY_CLIENT_SECRET")
    SPOTIFY_REDIRECT_URI = os.environ.get("SSPIDERR_SPOTIFY_REDIRECT_URI")
    SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative"
    # "Best hits" playlist shown on the home page.
    SPOTIFY_BEST_HITS_PLAYLIST_ID = os.environ.get("SPOTIFY_BEST_HITS_PLAYLIST_ID", "5iwkYfnHAGMEFLiHFFGnP4")

    LAST_FM_API_KEY = os.environ.get("LAST_FM_API_KEY")
    GOOGLE_CLOUD_API_KEY = os.environ.get("GOOGLE_CLOUD_API_KEY")
    GOOGLE_SEARCH_ENGINE_ID = os.environ.get("CX")
    NEWS_DATA_API_KEY = os.environ.get("NEWS_DATA_API_KEY")

    # --- Contact form -----------------------------------------------------
    MAIL_ADDRESS = os.environ.get("EMAIL_KEY")
    MAIL_APP_PASSWORD = os.environ.get("PASSWORD_KEY")
    CONTACT_RECIPIENT = os.environ.get("CONTACT_RECIPIENT") or os.environ.get("EMAIL_KEY")

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
