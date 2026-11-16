"""Capture fresh screenshots of SSPIDERR for the About pages.

    cd SSPIDERR-APP
    ..\\.venv\\Scripts\\python tools\\screenshots\\capture.py            # all shots
    ..\\.venv\\Scripts\\python tools\\screenshots\\capture.py home-hero  # just some

What it does
------------
1. Builds a throwaway demo database in tools/screenshots/.demo/ (git-ignored):
   public chart data and news are copied from instance/my_songs.db, but NO real
   users, emails or comments - a demo user, demo comments, reviews, playlists
   and a finished upload run are created instead.
2. Starts the app on http://127.0.0.1:5077 with a fake Spotify connection, so
   your real Spotify account is never used.
3. Opens each page in headless Chromium (Playwright) and saves a JPEG to
   static/img/about/<name>.jpg.

Requires the dev dependencies:  pip install -r requirements-dev.txt
and once:                       python -m playwright install chromium
"""
import io
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]                  # SSPIDERR-APP/
sys.path.insert(0, str(ROOT))

DEMO_DIR = ROOT / "tools" / "screenshots" / ".demo"
OUT_DIR = ROOT / "static" / "img" / "about"
REAL_DB = ROOT / "instance" / "my_songs.db"
PORT = 5077
BASE = f"http://127.0.0.1:{PORT}"
DEMO_EMAIL, DEMO_PASSWORD = "demo@sspiderr.app", "demo-password-123"
DEMO_SPOTIFY_ID = "sspiderr-demo"

PLAYLIST_NAMES = ["Road Trip", "Afrobeats Mix", "Chill Evenings", "Workout Hype", "Throwbacks", "Late Night Focus"]


# --------------------------------------------------------------------------
# Fake Spotify (only for the logged-in demo user)
# --------------------------------------------------------------------------
class DemoSpotify:
    def __init__(self, playlists, tracks):
        self._playlists, self._tracks = playlists, tracks

    def me(self):
        return {"id": DEMO_SPOTIFY_ID}

    def current_user_playlists(self, limit=50):
        return {"items": self._playlists, "next": None}

    def next(self, _results):
        return None

    def playlist(self, playlist_id, fields=None, **_):
        pl = next((p for p in self._playlists if p["id"] == playlist_id), self._playlists[0])
        return {"id": pl["id"], "name": pl["name"], "description": pl["description"], "images": pl["images"],
                "owner": pl["owner"], "external_urls": {"spotify": "https://open.spotify.com"}}

    def playlist_items(self, playlist_id, **_):
        return {"items": self._tracks.get(playlist_id, []), "next": None}

    def playlist_add_items(self, *_args, **_kwargs):
        return {"snapshot_id": "demo"}

    def user_playlist_create(self, user, name, description="", **_):
        return {"id": "demo-new"}


def _track_entry(t, popularity):
    return {"track": {
        "id": t["id"], "name": t["name"], "type": "track", "uri": f"spotify:track:{t['id']}",
        "album": {"name": t.get("album") or "", "images": [{"url": t["image"]}] if t.get("image") else []},
        "artists": [{"name": a.strip()} for a in (t.get("artist") or "Unknown").split(" ft. ")[0].split(",")],
        "duration_ms": 180_000 + (popularity * 997) % 60_000, "popularity": popularity,
        "preview_url": t.get("preview_url"), "external_urls": {"spotify": "https://open.spotify.com"},
    }}


# --------------------------------------------------------------------------
# Demo database
# --------------------------------------------------------------------------
def build_demo(app):
    from werkzeug.security import generate_password_hash

    from app.extensions import db
    from app.models import (
        BlogPost,
        Comment,
        HomeData,
        ReviewComment,
        SchedulerStatus,
        Songs,
        UploadJob,
        UploadJobItem,
        User,
    )

    real = sqlite3.connect(REAL_DB)
    real.row_factory = sqlite3.Row
    home = dict(real.execute("select * from home_data order by id desc limit 1").fetchone())
    posts = [dict(r) for r in real.execute(
        "select * from blog_posts where img_url not like '%music_blog_def_image%' order by date desc limit 40")]
    real.close()

    import json
    for key in ("top_albums", "feature_artists_info", "artist_description", "top_artist_album_track",
                "best_2025_hits", "this_weeks_hits", "artist_section_dict"):
        home[key] = json.loads(home[key]) if home.get(key) else None

    with app.app_context():
        db.drop_all()
        db.create_all()
        now = datetime.now(timezone.utc)
        db.session.add(SchedulerStatus(job_name="home_feed", last_run=now))
        db.session.add(SchedulerStatus(job_name="news_feed", last_run=now))
        home.pop("id", None)
        home["created_at"] = now
        db.session.add(HomeData(**{k: v for k, v in home.items() if hasattr(HomeData, k)}))
        for p in posts:
            p.pop("id", None)
            p["date"] = datetime.fromisoformat(p["date"]) if p.get("date") else now
            if p.get("tags"):
                p["tags"] = json.loads(p["tags"])
            db.session.add(BlogPost(**{k: v for k, v in p.items() if hasattr(BlogPost, k)}))

        pw = generate_password_hash(DEMO_PASSWORD)
        demo = User(email=DEMO_EMAIL, password=pw, spotify_acc_tok="demo", spotify_ref_tok="demo",
                    spotify_user_id=DEMO_SPOTIFY_ID, spotify_token_expires_at=int(time.time()) + 10 ** 7)
        ada = User(email="ada.music@sspiderr.app", password=pw)
        tunde = User(email="tunde.beats@sspiderr.app", password=pw)
        db.session.add_all([demo, ada, tunde])
        db.session.flush()

        article = BlogPost.query.order_by(BlogPost.date.desc()).first()
        for i, (user, text) in enumerate([
            (ada, "<p>Finally some good news this week. Can't wait for the tour dates!</p>"),
            (tunde, "<p>Been listening to this on repeat. The production is unreal.</p>"),
            (demo, "<p>Added the whole album to my Road Trip playlist straight from SSPIDERR.</p>"),
        ]):
            db.session.add(Comment(text=text, author_id=user.id, post_id=article.id,
                                   created_at=(now - timedelta(hours=5 - i * 2)).replace(tzinfo=None)))
        for user, text in [(ada, "I found three new favourite artists in one evening. Love the charts!"),
                           (tunde, "Uploading my old MP3s and getting a Spotify playlist back is magic."),
                           (demo, "Clean, fast and the Afrobeats charts are always fresh.")]:
            db.session.add(ReviewComment(text=text, author_id=user.id))

        # Demo playlists from public chart songs.
        songs = [t for t in (home["best_2025_hits"] or []) + (home["this_weeks_hits"] or []) if t]
        songs = [{"id": t.get("id") or t.get("spotify_song_id"), "name": t["name"], "artist": t["artist"],
                  "image": t.get("image"), "album": t.get("album"), "preview_url": t.get("preview_url")}
                 for t in songs if (t.get("id") or t.get("spotify_song_id"))]
        covers = [a.get("artwork_medium") or a.get("artwork_url_original") for a in home["top_albums"] or []] or [None]
        playlists, tracks = [], {}
        for i, name in enumerate(PLAYLIST_NAMES):
            pid = f"demo{i}"
            chosen = [songs[(i * 3 + j) % len(songs)] for j in range(8 + i * 2)]
            entries = [_track_entry(t, 55 + (j * 7) % 40) for j, t in enumerate(chosen)]
            tracks[pid] = entries
            playlists.append({"id": pid, "name": name, "owner": {"id": DEMO_SPOTIFY_ID, "display_name": "demo"},
                              "collaborative": False, "tracks": {"total": len(entries)},
                              "images": [{"url": covers[i % len(covers)]}] * 2, "description": "Made with SSPIDERR",
                              "public": True, "snapshot_id": f"s{i}"})
            for e in entries:
                t = e["track"]
                db.session.add(Songs(track_id=t["id"], name=t["name"][:100], album=t["album"]["name"][:100],
                                     artist=t["artists"][0]["name"][:100], duration_ms=t["duration_ms"],
                                     popularity=t["popularity"], preview_url=None, external_url="",
                                     spotify_playlist_id=pid, spotify_user_id=DEMO_SPOTIFY_ID))

        # A finished upload run (step 3 screenshot) + pending files (step 1/2 screenshots).
        job = UploadJob(public_id=str(uuid.uuid4()), user_id=demo.id, playlist_id="demo0", playlist_name="Road Trip",
                        state="done", total_files=7, processed_files=7, created_at=now, finished_at=now,
                        message="Done! Recognised 6 of 7 songs and added 4 new songs to Road Trip. "
                                "1 was already in the playlist, so we didn't add it again.")
        results = [
            ("01 - blinding lights.mp3", "Blinding Lights", "The Weeknd", True, True, None),
            ("burna_last_last.mp3", "Last Last", "Burna Boy", True, True, None),
            ("calm down remix.m4a", "Calm Down", "Rema & Selena Gomez", True, True, None),
            ("levitating.mp3", "Levitating", "Dua Lipa", True, None, "already"),
            ("essence (live).mp3", "Essence", "Wizkid", True, True, None),
            ("voice memo 12.m4a", None, None, False, None, None),
            ("old_mixtape_track3.mp3", "Mixtape Intro", "DJ Unknown", True, False, "Not found on Spotify"),
        ]
        for fname, title, artist, rec, added, extra in results:
            job.items.append(UploadJobItem(filename=fname, title=title, artist=artist, recognized=rec, added=added,
                                           already_in_playlist=(extra == "already"),
                                           error=extra if extra not in (None, "already") else None))
        db.session.add(job)
        db.session.commit()

        pending = Path(app.instance_path) / "uploads" / str(demo.id) / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        for name in ["Asake - Lonely At The Top.mp3", "Tems - Free Mind.mp3", "Davido - Unavailable.mp3",
                     "Ayra Starr - Rush.m4a", "Omah Lay - Soso.mp3"]:
            (pending / name).write_bytes(b"ID3demo")

        return {
            "job": job.public_id, "playlist": "demo0", "article": article.created_id,
            "song": songs[0]["id"],
            "album": home["album_id"] or (home["feature_artists_info"] or {}).get("album_id"),
            "artist": home["artist_name"],
            "demo": DemoSpotify(playlists, tracks),
        }


def start_server(app):
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", PORT, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --------------------------------------------------------------------------
# Shots
# --------------------------------------------------------------------------
HIDE_CHROME = """
  #ss-toasts, #scrollUp { display: none !important; }
  .sticky-wrapper { height: auto !important; }
  .oneMusic-main-menu { position: absolute !important; top: 0; }
  *, *::before, *::after { animation-duration: 0s !important; transition: none !important; }
  [data-animation], .wow { visibility: visible !important; opacity: 1 !important; animation: none !important; }
"""


def shots(ids):
    """(name, url, how). `how`: 'view' | ('el', selector) | callable(page) -> element or None."""
    def open_picker(page):
        page.locator("[data-add-track]").first.click()
        page.wait_for_selector(".ss-modal.open .ss-pl-item", timeout=20_000)
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.wait_for_timeout(600)
        return None                                   # viewport shot

    def charts_loaded(page):
        page.wait_for_selector("#top-charts-results .ss-chart-row", timeout=120_000)
        page.wait_for_timeout(1500)
        return page.locator("#top-charts")

    def job_done(page):
        page.wait_for_selector("#job-results:not([hidden])", timeout=30_000)
        page.wait_for_timeout(800)
        return page.locator("#job-card")

    return [
        ("home-hero", "/", "view"),
        ("home-cards", "/", ("el", ".oneMusic-buy-now-area")),
        ("home-charts", "/", ("el", ".miscellaneous-area")),
        ("charts", "/see-whats-new", charts_loaded),
        ("afro-hero", "/afro-beats", "view"),
        ("afro-lists", "/afro-beats", ("el", "section.ss-section")),
        ("song", f"/song-page/{ids['song']}", "view"),
        ("add-to-playlist", f"/song-page/{ids['song']}", open_picker),
        ("album", f"/album-page/{ids['album']}", "view"),
        ("album-tracks", f"/album-page/{ids['album']}", ("el", "section.ss-section.soft")),
        ("artist", f"/artist-page/{ids['artist']}", "view"),
        ("artist-tracks", f"/artist-page/{ids['artist']}", ("el", "section.ss-section.soft")),
        ("news", "/news-blog", ("el", ".blog-area")),
        ("article", f"/blog-post/{ids['article']}", "view"),
        ("comments", f"/blog-post/{ids['article']}", ("el", "#comments")),
        ("upload-1", "/loader-page", ("el", "section.ss-section")),
        ("upload-2", "/display-uploads", ("el", "section.ss-section")),
        ("upload-3", f"/song-processing/{ids['playlist']}?job={ids['job']}", job_done),
        ("playlists", "/playlist", ("el", "section.ss-section")),
        ("playlist-page", f"/playlist-page/{ids['playlist']}", "view"),
        ("playlist-tracks", f"/playlist-page/{ids['playlist']}", ("el", "section.ss-section")),
        ("suggestions", "/suggested-songs", ("el", "section.ss-section")),
        ("create-playlist", "/create-playlist", ("el", ".login-area")),
        ("time-travel", "/top-hits-time-travel?date=1999-12-25", "view"),
        ("awards", "/award-winning-songs", ("el", "section.ss-section")),
        ("home-mobile", "/", "mobile"),
        ("article-mobile", f"/blog-post/{ids['article']}", "mobile"),
    ]


def save(png_bytes, name, max_height=1500):
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if img.height > max_height:
        img = img.crop((0, 0, img.width, max_height))
    if img.width > 1600:
        img = img.resize((1600, round(img.height * 1600 / img.width)), Image.LANCZOS)
    path = OUT_DIR / f"{name}.jpg"
    img.save(path, "JPEG", quality=82, optimize=True, progressive=True)
    return path, img.size


def capture(only=None):
    from playwright.sync_api import sync_playwright

    import app.blueprints.library as library
    import app.services.spotify as spotify_service
    import app.services.uploads as uploads
    import app.utils as utils
    from app import create_app

    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    DEMO_DIR.mkdir(parents=True)
    app = create_app("production", instance_path=DEMO_DIR / "instance",
                     SQLALCHEMY_DATABASE_URI=f"sqlite:///{(DEMO_DIR / 'demo.db').as_posix()}",
                     SCHEDULER_ENABLED=False, CACHE_DIR=str(ROOT / "instance" / "cache"),
                     RATELIMIT_ENABLED=False)
    ids = build_demo(app)
    fake = ids.pop("demo")
    for module in (spotify_service, utils, uploads):
        module.user_client = lambda *a, **k: fake
    library.spotify_service.start_library_sync = lambda *a, **k: None

    server = start_server(app)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wanted = [s for s in shots(ids) if not only or s[0] in only]
    print(f"Capturing {len(wanted)} screenshots from {BASE} ...")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            desktop = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                         is_mobile=True, has_touch=True)
            for ctx in (desktop, mobile):
                page = ctx.new_page()
                page.goto(f"{BASE}/login-page")
                page.fill("#login-email", DEMO_EMAIL)
                page.fill("#login-password", DEMO_PASSWORD)
                page.click("button[type=submit]")
                page.wait_for_load_state("networkidle")
                page.close()

            for name, url, how in wanted:
                ctx = mobile if how == "mobile" else desktop
                page = ctx.new_page()
                start = time.time()
                page.goto(BASE + url, wait_until="domcontentloaded", timeout=180_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=45_000)
                except Exception:
                    pass
                page.add_style_tag(content=HIDE_CHROME)
                page.wait_for_timeout(1200)                          # carousels / lazy images settle
                target = None
                if callable(how):
                    target = how(page)
                elif isinstance(how, tuple):
                    target = page.locator(how[1]).first
                if target is not None:
                    target.scroll_into_view_if_needed()
                    page.wait_for_timeout(800)
                    data = target.screenshot()
                else:
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(300)
                    data = page.screenshot()
                path, size = save(data, name, max_height=1700 if how == "mobile" else 1500)
                print(f"  {name:<18} {size[0]}x{size[1]}  {path.stat().st_size // 1024:>4} KB  ({time.time() - start:.1f}s)")
                page.close()
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    capture(set(sys.argv[1:]) or None)
