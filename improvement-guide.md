# SSPIDERR: Improvement Guide

_Written 2026-11-10 against branch `index-efficiency` (HEAD `c4d9421` plus the uncommitted `main.py` change)._
_All line numbers refer to `one-music-gh-pages/main.py` unless another file is named._

This guide supersedes `PROJECT_ANALYSIS.txt` (2026-11-09). Everything in that file was checked against the code again. Two of its points are corrected in §0, and about 30 problems it didn't cover are added here.

---

## Status (2026-11-14, branch `claude-test`)

**Every item below has been worked through.** The implementation is on `claude-test` in these commits:

| Commit | What |
|---|---|
| `af9f23f` `f9d4ed3` | your pending thread fix; template folders removed (R1) |
| `f0762a4` | IDE/cache/scratch files untracked (R2, R8) |
| `b211082` | images and assets: static/ 126 MB → 15 MB (R3) |
| `8dc8a3b` | main.py split into `app/` (A1–A3, A6) + all bug, security, performance and UI fixes |
| `418ef33` | Flask-Migrate baseline + refactor migration (A6) |
| `a1238b0` | 180 pytest tests + GitHub Actions CI (T1–T5) |
| `0a4bdc9` | fixes found while running against the live APIs |
| (docs) | README (R5), CLAUDE.md (R6), this status section |

**Corrections to this guide found while implementing:**
- **B1**: the date fields are `<input type="date">`, which already sends `YYYY-MM-DD`. The real bug was that the page's JavaScript never sent the date at all. Both are fixed.
- **R4/A7**: Flask-Gravatar *is* used (comment avatars), but it is incompatible with Flask 3, so it was replaced by a small `gravatar` filter instead of being removed.
- **New bugs not in the guide:**
  - The home-page `<audio>` players used an iTunes *web page* URL as the source, so previews never played.
  - The news list read `post.description`, which doesn't exist, so every excerpt was empty.
  - `/award-winning-songs` crashed. US Top 40, Time Travel and Suggestions were empty stubs.
  - The About page contact form posted to `#`.
  - The playlist page showed a hard-coded "5 Awards Won".
  - 14 of the 74 Billboard chart options were misspelled slugs that return 404.
  - A stray `*/` in style.css disabled the theme's reset rule.
  - Failed HTTP requests logged URLs containing API keys.
- **A7 (Spotify)**: confirmed live. `related-artists` and Spotify editorial playlists return 404 for this app. Similar artists now come from Last.fm.
- **A4**: kept and fixed `should_run_24h_task()` as requested, rather than deleting it. It now drives one global job, see `app/tasks.py`.

**Still needs you:**
- Log in with your real account and try *Add to playlist*, *Create playlist* and an upload → recognise → playlist run. These were tested with fakes only, so that your real Spotify tokens weren't touched.
- The Google Custom Search key in `.env` returns HTTP 403. Either remove it or fix the key. Because it appeared in a local log file during testing (now deleted), rotating it is sensible.
- Optional: set `SCHEDULER_TIMEZONE=Africa/Lagos` in `.env` so the daily refresh happens at Lagos midnight instead of UTC midnight.
- History still contains the old large images (`.git` ≈ 177 MB). Shrinking it means rewriting history (R3, `git filter-repo`), so only do it if you want to.

How to use this guide: work through the **phases in order** (§9). Every item has an ID (e.g. `B7`) so you can mention it in commit messages and Claude prompts, for example "Fix B7 and B8 from improvement-guide.md".

---

## Contents

0. [Corrections to the previous analysis](#0-corrections-to-the-previous-analysis)
1. [Repository and workflow hygiene](#1-repository-and-workflow-hygiene) (`R*`)
2. [Bugs: things that are wrong today](#2-bugs--things-that-are-wrong-today) (`B*`)
3. [Security](#3-security) (`S*`)
4. [Performance](#4-performance) (`P*`)
5. [Architecture and code structure](#5-architecture-and-code-structure) (`A*`)
6. [Templates and front-end](#6-templates-and-front-end) (`F*`)
7. [Testing](#7-testing) (`T*`)
8. [Using Claude Code and subagents to go faster](#8-using-claude-code-and-subagents-to-go-faster)
9. [Suggested roadmap](#9-suggested-roadmap)

---

## 0. Corrections to the previous analysis

| Claim in `PROJECT_ANALYSIS.txt` | What the code actually does |
|---|---|
| 3.2: "when the token is refreshed it saves only the new access token and drops any new refresh token" | Not quite. spotipy's `refresh_access_token()` puts the old refresh token back if Spotify doesn't send a new one, and then calls the cache handler's `save_token_to_cache`, which saves both tokens. **The real bug is *who* gets saved**: the cache handler is built with `current_user` (line 2695), not the `user` argument, so the refresh is written to whoever is logged in. Inside a worker thread that is no one, and the call fails. |
| "Uncommitted change… is correct and safe to commit" | **Confirmed safe, with a caveat.** `refresh_user_library` now passes a Spotify user-id *string* to `get_playlist_tracks(user, sp, …)`. That works only because `sp` is always supplied, so `user` is never read (line 2801). The parameter name now misleads readers. Rename it to `user_or_none` or remove it (see A3). |
| 3.1: the `current_user` thread bug "fails" | It doesn't crash. It **silently falls back to the app-level Spotify client** because of the bare `except Exception` at line 852. The same thing happens at lines 932 (inside `get_live_global_top_tracks`), 1334, 1655 and 1657. Fix it anyway: every call wastes time on a failed lookup and hides real errors. |

---

## 1. Repository and workflow hygiene

### R1. Settle the 456 unstaged deletions *(do this first)*
`Imperial/`, `KnightOne/`, `Siimple/` and `SnapFolio/` are deleted on disk but still tracked. They are old BootstrapMade templates that have nothing to do with the app.
```powershell
git rm -r --cached Imperial KnightOne Siimple SnapFolio
git commit -m "Remove unused BootstrapMade template folders"
```
If you still want them, restore them with `git restore .` and move them to a separate repo.

### R2. Stop tracking junk files
- `one-music-gh-pages/ffcache*`: three Firefox cache dumps of 4.4 MB each.
- `one-music-gh-pages/.sass-cache/`: build artefacts.
- `.idea/`: PyCharm settings. They are user-specific, and `misc.xml` still points at a "Day 37" interpreter.
- `one-music-gh-pages/static/uploads/`: user data. It must never be committed.
- `one-music-gh-pages/instance/my_songs.sqbpro`: a DB Browser project file.

Add to `.gitignore`:
```gitignore
.idea/
.sass-cache/
ffcache*
one-music-gh-pages/static/uploads/
*.sqbpro
```
Then `git rm -r --cached .idea one-music-gh-pages/.sass-cache one-music-gh-pages/ffcache*` and commit.

### R3. Images are 113 MB and some are 20 MB each
`.git` is already 177 MB. The worst files:

| File | Size | Used by |
|---|---|---|
| `static/img/front-view-man-holding-cassette.jpg` | 19.6 MB | `tooplate-style.css` |
| `static/img/multimedia-entertainment-music-bars-display.jpg` | 9.0 MB | `tooplate-style.css` |
| `static/img/black-boy-posing-with-headphones.jpg` | 4.9 MB | `tooplate-style.css` |
| `static/img/lightbox-still-life-arrangement(.jpg)` | 10 MB + 8.6 MB | **unused**, and one copy has no file extension |
| `static/img/black-cassette-tape-…`, `paisaje-verde-…`, `bg-img/imagine_dragons.jpg` | 4.5 to 5.9 MB | **unused** |

What to do: delete the unused images. Resize the used ones to at most 1920 px wide and convert them to WebP or compressed JPEG. Each should end up around 200 to 400 KB. A 20 MB hero image makes the page slow on any phone. History will keep the old blobs. If repo size matters, run `git filter-repo --strip-blobs-bigger-than 2M` once, coordinated with the remote, because it rewrites history.

### R4. Make the environment reproducible
There is no `requirements.txt` or `pyproject.toml`. The current `.venv` also has **three competing packages that all install `flask_bootstrap`**: `Flask-Bootstrap 3.3.7.1`, `Bootstrap-Flask 2.3.3` and `flask-bootstrap5 0.1.dev1`. Which one wins depends on install order. The app needs **Bootstrap-Flask** (`Bootstrap5`, `bootstrap5/form.html`).
```powershell
.venv\Scripts\pip uninstall -y Flask-Bootstrap flask-bootstrap5
.venv\Scripts\pip install --force-reinstall Bootstrap-Flask
```
Unused dependencies to drop once A1 is done: `numpy` (only `default_fill_value` is imported, line 25, and never used), `dominate` (line 15), `billboard` (line 56; the code uses its own scraper), `Flask-Gravatar` (initialised at line 136, never used in a template).

Then write a pinned `requirements.txt`. List only the packages you actually import, not a raw `pip freeze`: Flask, Flask-Login, Flask-SQLAlchemy, Flask-WTF, Flask-CKEditor, Bootstrap-Flask, SQLAlchemy, spotipy, shazamio, requests, beautifulsoup4, feedparser, python-dateutil, pytz, python-dotenv.

Also add an `.env.example` with every key name and no values. The app reads 20 environment variables: `APP_SECRET_KEY`, `SSPIDERR_SPOTIFY_*`, `UNSPLASH_*`, `LAST_FM_*`, `GOOGLE_CLOUD_API_KEY`, `CX`, `NEWS_DATA_API_KEY`, `EMAIL_KEY`, `PASSWORD_KEY`, `CLOUDINARY_*`.

### R5. Fix the README
`README.md` is saved as **UTF-16** and has the heading three times. GitHub shows it as garbage. Re-save it as UTF-8 with a short description, how to run it (`pip install -r requirements.txt`, copy `.env.example`, `python main.py`), and the list of external APIs used.

### R6. Give this repo its own `CLAUDE.md`
Claude Code currently picks up `C:\Users\pc\Downloads\CLAUDE.md`. That file describes a **LangChain bootcamp project**, not SSPIDERR, and it tells Claude things like "use uv" and "Python ≥3.13" that don't apply here. Create `SPIDER WEB APP/CLAUDE.md` (run `/init`) that covers:
- what the app is, where the code lives (`one-music-gh-pages/`) and how to run it
- the rules from this guide (e.g. "never pass `current_user` into a thread", "every `requests.get` gets a `timeout=`")
- "Don't commit `.env`, `instance/` or `static/uploads/`."

Moving the LangChain `CLAUDE.md` into the LangChain project's own folder fixes the root cause.

### R7. Commit and branch habits
- Recent commit messages ("Still working on 24hrs Task", "Error in threading playlist. Please return", "FOR NOW!") don't say what changed. Use `<area>: <what changed>` instead, e.g. `scheduler: move 24h refresh to background job`, and put TODOs in the code or in GitHub issues, not in commit messages.
- Keep one branch per topic and merge it to `main` with a PR, even when working solo. The PR diff is where `/code-review` (§8) does its best work.
- Leftover TODO/scratch comments in the code (`## We had an error here please return back`, `## Testing, remove if not ok`, `#NOTE: Make sure you uncomment after testing`) should become GitHub issues.

### R8. Clean up the scratch scripts
`test.py` (794 lines) is an older copy of the scraping and recognition pipeline. `awards-test.py` is a Grammy scraper experiment. Neither is a test. Either move them to `scratch/` (and gitignore it) or delete them once the real code is modularised (A1). Keep the `(file, title, artist)` refactor idea in `test.py:510-617`, because it is a good sketch for A5.

---

## 2. Bugs: things that are wrong today

Ordered by how much users feel them.

### B1. "See what's new" ignores the chosen date (line 3174)
```python
formatted_date = date_obj.strftime("%Y-%m-%d")       # computed…
chart_result, endpoint_type = billboard_scraper(chart_option, date_str)  # …but the raw "10/20/2025" is sent
```
Billboard gets `/charts/hot-100/10/20/2025`, which is the wrong URL. **Fix:** pass `formatted_date`.

### B2. The Billboard artist cleaner removes every letter "x" (line 3112)
```python
s = re.sub(r"[&xX\+]", ",", s)
```
This turns "Alex Warren" into "Ale, Warren" and "Lil Nas X" into "Lil Nas ,". Only a standalone `x` between artists should be replaced:
```python
s = re.sub(r"\s+(?:&|x|X|\+)\s+", ", ", s)
```

### B3. A playlist without a cover crashes the page (lines 2789-2793)
`get_playlist_tracks` returns `"image"` as a **URL string** (line 2826), but the fallback treats it as a list of image dicts:
```python
if image_size < len(tracks[0]["image"]):         # length of a string
    return tracks[0]["image"][image_size]['url'] # 'h'['url'] -> TypeError
```
Any user who has an empty or cover-less playlist hits a 500 on `/`, `/playlist`, `/afro-beats` and every other page with the playlist modal. **Fix:** `return tracks[0]["image"]`.

### B4. `get_playlist_tracks` crashes on local files and episodes (line 2826)
`track['album']['images'][0]` raises `IndexError` when a playlist contains a local file or a podcast episode, because these have no images. Use:
```python
images = (track.get('album') or {}).get('images') or []
"image": images[0]['url'] if images else None,
"popularity": track.get('popularity', 0),
```

### B5. Stale or missing loop variables in `see_whats_new_results` (lines 3186-3189, 3235-3239)
When a Spotify search finds nothing, `album_id`, `album_image` and `track_id` are either **undefined** (first iteration, so `UnboundLocalError`) or **left over from the previous row**, so the chart shows the wrong cover and links to the wrong song. Reset them to `None` at the top of each loop iteration.

### B6. One failing API takes down the home page (lines 1124-1142)
`results = {key: future.result() …}` re-raises any exception from a worker. So if Billboard returns 403 (it often blocks scrapers), or `fetch_json` hits `raise_for_status`, `/` returns a 500. The `try/except` at line 1139 never catches anything, because it only wraps a dict lookup. **Fix:** collect each result on its own:
```python
def safe(fut, default=None):
    try:
        return fut.result(timeout=20)
    except Exception as e:
        app.logger.warning("home fetch failed: %s", e)
        return default
results = {k: safe(f) for k, f in futures.items()}
```
Then make every downstream use cope with `None`. `album_name`, `song_name` and `top_album_id` can currently be unbound when the iTunes call *and* the Deezer fallback both fail (lines 1148-1184).

### B7. `new_time_tag` is fixed when the server starts (line 1070)
`new_time_tag = datetime.now(timezone.utc)` is evaluated **once, when the module loads**. Every `HomeData` row then carries the server start time, not the time its data was fetched. After a restart, `HomeData.query.filter_by(new_time_tag=new_time_tag)` (line 1285) matches nothing, and the code falls into the "Testing, remove if not ok" branch. Use a per-row `created_at` default (`server_default=func.now()`) and query "the newest row".

### B8. The home page crashes when no data matches (line 1300)
In the `else` branch, `data` comes from `filter_by(user_id=current_user_id)`, which can return `None`. Example: a user logs in on a server that already has fresh anonymous data, so the row's `user_id` is `None`. `data.top_albums` then raises `AttributeError`. This is fixed properly by A4 (one shared `HomeData`). Until then, guard it: `if data is None: <run the fetch path>`.

### B9. 29 views return `None` (500 Internal Server Error)
Grep for `return None  # User not logged in`. It appears in `home`, `playlist`, `playlist_page`, `afro_beats`, `song_page`, `artist_page`, `album_page`, `see_whats_new`, `see_whats_new_results`, `loader_page`, `song_processing_stream`, `display_uploads`, plus `album_page`'s Deezer error at line 2541. A Flask view must return a response. Replace with:
```python
return redirect(url_for('spotify_login'))   # logged in but Spotify not connected
```
or render the page without the playlist modal.

### B10. Anonymous visitors crash several routes
`/playlist`, `/loader-page`, `/display-uploads`, `/song-processing-stream/<id>`, `/callback` and `POST /about-us` have **no `@login_required`**, but they touch `current_user.spotify_acc_tok`, `current_user.spotify_user_id` or `current_user.id`. `AnonymousUserMixin` has none of these attributes, so the request raises `AttributeError` and returns a 500. Add `@login_required` and set `login_manager.login_view = "login_page"`.

### B11. `user_loader` returns 404 instead of logging the user out (line 133)
`db.get_or_404(User, user_id)` inside `@login_manager.user_loader` means that a deleted user's leftover cookie returns 404 on **every** page. The loader must return `None`:
```python
return db.session.get(User, int(user_id))
```

### B12. `get_valid_spotify_token` problems (lines 2687-2727)
1. It builds `DBTokenCache(current_user, db)` instead of `DBTokenCache(user, db)` (see §0).
2. It calls `sp.current_user()` **on every call** to test the token. That is an extra Spotify round trip on every page view, sometimes several per page.
3. Any non-401 error (e.g. **429 rate limit**) is re-raised and shows up as a 500.

**Fix:** store `spotify_token_expires_at` on `User` and refresh only when `expires_at - 60 < now`. Let spotipy handle this: `SpotifyOAuth(cache_handler=DBTokenCache(user, db))` + `sp_oauth.validate_token(cache_handler.get_cached_token())` refreshes automatically when the cached dict includes `expires_at`. Update `DBTokenCache.save_token_to_cache` (`classes.py:22`) to store `expires_at` too, and to keep the existing refresh token when the new response has none.

### B13. Login never saves the scheduler update (line 2037)
`status.last_run = now` is set, but the code never calls `db.session.commit()`. The whole block becomes unnecessary after A4. Until then, add the commit.

### B14. The scheduler's run counter is shared by every visitor (lines 353-452)
`number_of_run` is a module-level global, so the first visitor after a restart changes the logic for everyone. Your own comment at line 355 names the second problem: someone who stays on the site never gets fresh data. The real fix is A4. Delete `should_run_24h_task`, `SchedulerStatus` and `get_session_id` once A4 is in place.

### B15. News: `db_date` is undefined or carried over (lines 1768-1772, 1815-1819)
When an article has no date, the `else`/`except` branch sets `year`, `month` and `day`, but **not `db_date`**. The first such article raises `UnboundLocalError`. Later ones silently reuse the previous article's date. `BlogPost.date` is also `nullable=False`. Set `db_date = datetime.now(timezone.utc)` in those branches.

### B16. `/news-blog` crashes when `HomeData` is empty (lines 1938-1958)
`album_name`, `album_id`, `song_name` and the others are only assigned inside `if notice_data:`. On a fresh database the page raises `UnboundLocalError`. Initialise them all to `None` (or defaults) before the `if`. The `… if notice_data else "static/img/…"` fallbacks inside the `if` can never run.

### B17. `/about-us` POST (lines 1704-1715)
It needs `@login_required` (or a check), and empty text must be rejected. `ReviewComment.text` is `nullable=False`, so an empty form raises `IntegrityError`.

### B18. `artist_page` crashes when Spotify has no album for the artist (line 2374)
`top_artist_info` returns `{}` when nothing is found, so `artist_info['album_name']` raises `KeyError`. The same thing happens at line 1354 in `home()` and line 1651 in `afro_beats`. Use `.get()` and skip the section.

### B19. `album_page` has several unbound variables (lines 2503-2684)
- `tracks_data`, `spot_album_data` and `album_image` are only set on some paths. Line 2631 (`spot_album_data`) and line 2645 (`tracks_data['items']`) raise `NameError` on the others.
- Line 2587: `spotify_album_data["albums"]["items"][0]` is applied to an **album object**, which has no `"albums"` key. This branch always fails.
- Line 2595 calls `sp.album_tracks(album_id)` with the *iTunes* id.

Initialise everything to `None` at the top of the function. Better: split it into `resolve_album(album_id) -> (spotify_album, itunes_album)` and a renderer.

### B20. `song_page`: the Deezer fallback can never run (lines 2098-2112)
`sp.track(song_id)` with an iTunes or Deezer numeric id **raises** `SpotifyException`. It never returns something falsy, so the `else:` Deezer branch is dead code, and the exception becomes a 500. Also, `sp.album(song_data['spotify']['album']['id'])` at line 2174 runs with `None` when no Spotify match was found. Wrap both lookups in `try`, and skip the album section when there is no id.

### B21. Song processing mixes up users and can run twice
- Recognised songs are selected **by `playlist_id` only** (line 3545) but deleted **by user** (line 3488). Two users working on the same collaborative playlist pick up each other's tracks. Filter by both.
- `static/uploads` is **one folder for everyone**, and **every visit to `/` deletes it** (line 1108). User B opening the home page wipes user A's in-progress upload.
- `STATUS` is one global dict (line 3361), so every user's progress screen shows everyone else's progress.
- The page starts the job with `new EventSource(...)` (`templates/song_processing.html:453`). The route isn't a stream: it runs for minutes and then redirects. If the connection drops (proxy timeout, laptop sleep), **EventSource reconnects automatically and starts the whole job again**, which adds duplicate songs to the playlist.

The fix is A5 (a background job with a job id). Small fixes you can make now:
- Line 3663: `if len(song_uris) % 100 == 0` is true while `song_uris` is empty, so every not-found track sleeps an extra 2 s. Use `if song_uris and len(song_uris) % 100 == 0`.
- Lines 3581-3582: the second search runs **even when the first one matched**. Run `result2` only when `result` is empty. That halves the Spotify calls.

### B22. The front-end calls `/api/status`, which doesn't exist
`templates/index.html:570` and `templates/display_uploads.html:336` call `fetch("/api/status")`, which returns 404. `fetch` doesn't throw on a 404, so the boot screen still fades out, but it is a wasted request and misleading. Point them at `/app-status`, or remove the call.

### B23. `/contact` fails on bad input
`data["name"]` raises `KeyError`, which Flask turns into a 400, when a field is missing. An SMTP failure (wrong app password, Gmail rate limit) is a 500 *after* the user has already seen nothing. Wrap `send_email` in `try/except smtplib.SMTPException`, flash an error, and log it. Move the hard-coded recipient address (line 3057) to an env var (`CONTACT_RECIPIENT`).

### B24. `top_albums_info` never uses its Deezer fallback (line 608)
`requests.get` *raises* on network errors and only returns a falsy `Response` for 4xx/5xx. A timeout therefore never reaches the `else: build_deezer_album_dataset` path. Wrap the call in `try/except requests.RequestException`.

---

## 3. Security

### S1. Stored XSS in comments *(high)*
`templates/blog_post.html:176` renders `{{ comment.text | safe }}`. Anyone can post `<img src=x onerror=…>` and it runs for every reader, with access to their session. Clean the HTML **before saving**:
```python
import nh3   # pip install nh3
clean = nh3.clean(form.comment_text.data, tags={"p","b","i","strong","em","a","ul","ol","li","br","blockquote"})
```
The same goes for `post.subtitle | safe` (`blog_post.html:141`), which is **third-party RSS HTML**, and the Last.fm summaries (`album.html:87`, `artist.html:99`, `song.html:91`, `index.html:292`). Clean them once when you fetch them.

### S2. No CSRF protection on most forms
Only `CommentForm` is a `FlaskForm`. Login, register, contact, create-playlist, about-us, delete-comment, upload and `/add_to_playlist` (JSON) are all unprotected. Add global protection:
```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
```
Then add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to each raw form. For `fetch()` calls, put `<meta name="csrf-token" content="{{ csrf_token() }}">` in `header.html` and send it as an `X-CSRFToken` header. For Dropzone, use `headers: {'X-CSRFToken': …}`.

### S3. Open redirect via `next` (lines 2041, 2946)
`redirect(request.args.get('next'))` sends users to any URL, e.g. `/login-page?next=https://evil.example`. Only accept relative paths:
```python
from urllib.parse import urlparse
def safe_next(url): return url if url and not urlparse(url).netloc and url.startswith('/') else None
```

### S4. `debug=True` (line 3725)
The Werkzeug debugger lets anyone who can reach the server run arbitrary Python. Use `app.run(debug=os.getenv("FLASK_DEBUG") == "1")`, and in production run under `waitress` (works on Windows) or `gunicorn`.

### S5. Weak password hashing (lines 2064-2068)
`pbkdf2:sha256` with `salt_length=8` is weaker than Werkzeug's default. Call `generate_password_hash(password)` with no other arguments. Old hashes still verify, because `check_password_hash` reads the method from the stored hash. There is also no minimum length or email validation on registration.

### S6. Upload endpoint
`/upload-song` has no login check, no size limit, and no per-user folder. Add:
```python
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 50 MB
```
plus `@login_required`, and save to `uploads/<user_id>/<job_id>/`. Also `secure_filename` can return `""` (e.g. for `"..mp3"`), so reject empty names. The extension check is fine, but you could also check the file signature (`mutagen` or `filetype`).

### S7. Secrets and personal data in code
- Line 71 builds a `CLOUDINARY_URL` string containing the API secret and never uses it. Delete it.
- Line 3057: the personal recipient address is hard-coded (see B23).
- `SECRET_KEY`: if `APP_SECRET_KEY` is missing, sessions silently break. Fail fast: `app.secret_key = os.environ["APP_SECRET_KEY"]`.
- `Gravatar(use_ssl=False)` loads images over HTTP (mixed content). It is also unused, so remove it.
- The OAuth `state` check in `/callback` is good. Keep it.

### S8. Rate limiting
Login, register, contact and upload have no throttling. `Flask-Limiter` with `"5/minute"` on login and contact is enough for a project of this size.

---

## 4. Performance

Pages are slow because the code makes a lot of external HTTP calls in a row inside each request. The biggest problems:

### P1. Playlist listing makes many calls per playlist (lines 2730-2759)
For **every** playlist, `get_user_playlists` calls:
- `get_playlist_image` → `sp.playlist(id)`, a full playlist fetch including the first 100 tracks, just for the image, which is **already in `item['images']`** in the listing
- `len(get_playlist_tracks(...))`, a full paginated download of every track, just to count them, which is **already in `item['tracks']['total']`**
- sometimes a second `get_playlist_tracks` and an Unsplash call

A user with 30 playlists of 200 tracks triggers about 100 Spotify requests on **every page that shows the playlist modal**. That is about 12 routes. Replace it with:
```python
for item in results['items']:
    imgs = item.get('images') or []
    playlists.append({
        "id": item['id'], "name": item['name'],
        "owner": item['owner']['display_name'],
        "tracks": item['tracks']['total'],
        "num_tracks": item['tracks']['total'],
        "image": (imgs[min(image_size, len(imgs)-1)]['url'] if imgs else PLACEHOLDER_URL),
        "description": item['description'], "public": item['public'],
    })
```
That is one call per 50 playlists. It is the biggest speed-up in the project. Also line 2752 uses the global `current_user` instead of the `user` parameter.

### P2. Fetch the playlist modal data on demand
Most pages fetch the user's playlists only for an "Add to playlist" modal that most visitors never open. Serve `/api/my-playlists` (JSON, cached for 5 minutes per user) and load it when the modal opens. Every logged-in page then renders without waiting for Spotify.

### P3. Remove repeated identical calls in `artist_page` (lines 2258-2498)
- `get_artist_image(artist_name, 4, sp)` runs **inside loops** at lines 2394 and 2438, so it performs the same Spotify search once per track. Call it once before the loop.
- `top_artist_info(r_artist_name)` runs for each of the 10 related artists (line 2452), which is 20 extra calls.
- `sp.album_tracks()` runs for **every album and single** (line 2335). A prolific artist can have more than 100. Sort albums by `release_date` first, then fetch tracks only for the newest 3 to 5.
- `sp.artist_albums` is called twice (lines 2302 and 2461).

### P4. Use Spotify's batch endpoints
`get_album_tracks_sorted` calls `sp.track()` once per track (line 783) just to read `popularity`. `sp.tracks(ids)` takes up to 50 ids in one call.

### P5. Timeouts and HTTP connection reuse
The file has **28 `requests.get` calls and 5 timeouts**. A single slow upstream (Billboard, NewsData) hangs a request forever. Create one shared session:
```python
HTTP = requests.Session()
HTTP.headers["User-Agent"] = "SSPIDERR/1.0"
adapter = requests.adapters.HTTPAdapter(max_retries=urllib3.util.Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503]))
HTTP.mount("https://", adapter); HTTP.mount("http://", adapter)
# then: HTTP.get(url, params=..., timeout=(3, 10))
```
The session reuses TCP/TLS connections, which saves 100 to 300 ms per call to the same host.

### P6. Cache external lookups
Artist images, artist descriptions and iTunes previews hardly change. Add `Flask-Caching` (SimpleCache, or FileSystemCache to survive restarts) with `@cache.memoize(timeout=86400)` on `get_artist_image`, `get_artist_description`, `get_itunes_preview` and `top_artist_info`. The same artists show up on the home, afro-beats, artist and see-what's-new pages.

### P7. Remove extra calls in `see_whats_new_results`
Line 3241 calls `get_artist_description` for every song (2 or 3 HTTP calls each) and **never uses the result**. Delete it. Run the 10 per-row lookups in a `ThreadPoolExecutor`, as `afro_beats` already does.

### P8. Run Deezer detail calls in parallel
`build_deezer_album_dataset` (line 546) fetches 50 album details one after another. Use a thread pool, or drop the detail call if `release_date` isn't shown.

### P9. No writes on GET and no work at import time
- `news_blog` runs `trim_news_table()` (a DELETE) on **every page view** (line 1904), then loads **every** post into memory to slice 5. Use `db.paginate(db.select(BlogPost).order_by(...), page=page, per_page=5)` and move trimming into the scheduled job.
- `load_news_to_db()` runs **at import time** (lines 1887-1888). Every restart (and every auto-reload with `debug=True`) waits on NewsData and Billboard, and a network error stops the app from starting. Move it into the scheduled job (A4).
- `home()` deletes and recreates the uploads folder on every visit (lines 1108-1109). Remove this (see B21).

### P10. Logging
There are 119 `print()` calls, many printing full API responses (`print(album_json)` at line 1150 prints about 100 KB per home load) and `inspect.currentframe()` lines. Switch to `app.logger` / `logging` with levels, and keep DEBUG off by default.

### P11. Database
- `HomeData` gets a **new row on every refresh and for every logged-in user** (lines 1250, 1362) and never shrinks. A4 fixes this. Until then, delete old rows when you insert.
- SQLite with background threads writing (`refresh_user_library`) and request threads writing at the same time can raise `database is locked`. Enable WAL mode:
  ```python
  from sqlalchemy import event
  @event.listens_for(db.engine, "connect")
  def _wal(dbapi_conn, _): dbapi_conn.execute("PRAGMA journal_mode=WAL")
  ```
  This must run inside an app context.
- Add indexes on `songs.spotify_user_id`, `songs.spotify_playlist_id` and `user_playlist.spotify_user_id`. These columns are filtered in every library refresh.
- `refresh_user_library` deletes **everything** and re-downloads every track on each `/playlist` visit. Compare each playlist's `snapshot_id` (included in the listing) and re-sync only the playlists that changed.

### P12. Static assets
Besides R3: both `jquery-2.2.4` and `jquery-3.2.1` are shipped, so check which one the pages load and delete the other. Add `loading="lazy"` to below-the-fold `<img>` tags. Set `SEND_FILE_MAX_AGE_DEFAULT` so browsers cache static files.

---

## 5. Architecture and code structure

### A1. Split `main.py` (3,726 lines) into a package
Suggested layout. Each file stays under about 400 lines:
```
one-music-gh-pages/
  app/
    __init__.py          # create_app(): config, db, login_manager, csrf, cache, blueprints
    config.py            # reads env vars once; Config / DevConfig / ProdConfig
    extensions.py        # db, login_manager, csrf, cache objects
    models.py            # User, BlogPost, Comment, ReviewComment, Playlist, Songs, *Songs, HomeData
    services/
      http.py            # shared requests.Session with timeouts and retries (P5)
      spotify.py         # client factory, token refresh, playlists, search helpers
      itunes.py  deezer.py  lastfm.py  unsplash.py  google_images.py
      scrapers.py        # billboard_scraper, get_billboard_top_artists, audio_mack_scrape
      news.py            # fetch_newsdata_news, fetch_billboard_news, load_news_to_db
      home_feed.py       # build_home_snapshot() used by the scheduler
      recognition.py     # shazam batch + spotify upload pipeline
    blueprints/
      main.py            # /, /about-us, /contact, /elements
      auth.py            # /login-page, /register-page, /logout, /spotify-login, /callback
      music.py           # /song-page, /artist-page, /album-page, /afro-beats, /see-whats-new*
      library.py         # /playlist, /playlist-page, /create-playlist, /add_to_playlist
      news.py            # /news-blog, /blog-post, /delete-comment
      uploads.py         # /loader-page, /upload-song, /display-uploads, /song-processing*, /status
    tasks.py             # APScheduler jobs (A4)
  templates/  static/
  run.py                 # from app import create_app; create_app().run()
```
When moving routes into blueprints, `url_for('home')` becomes `url_for('main.home')`. Grep the templates and update them in the same commit. **Move code without changing behaviour first, then fix things in separate commits.** That keeps every step easy to review and easy to bisect.

### A2. Remove the copy-pasted request boilerplate
These four lines appear in about 12 routes:
```python
access_token = get_valid_spotify_token(current_user)
if not access_token: return None
sp = spotipy.Spotify(auth=access_token)
playlist_list = get_user_playlists(current_user, sp, 1, "playlist", "small")
```
Every route then has **two nearly identical `render_template` calls** (logged-in vs. anonymous). Replace them with:
- a `@spotify_required` decorator that puts `g.sp` in place or redirects to `/spotify-login`
- a `@app.context_processor` (or P2's lazy endpoint) that provides `playlist_list` to every template, so each route has a single `render_template`

That removes about 300 lines.

### A3. Never use request-bound objects in worker threads
Write a rule for the project and add it to `CLAUDE.md` (R6): **resolve `current_user`, `session`, `request` and `url_for` in the request thread, and pass plain values (ids, token strings, a ready `sp` client) into executors.** Concretely:
- In `home()`, call `get_spotify_client_for_request(current_user)` *before* the pool and pass `sp` to `get_spotify_playlist_tracks(playlist_id, sp)`, `get_live_global_top_tracks(10, sp)`, `top_artist_info(name, sp)` and `get_album_tracks_sorted(name, sp)`, and drop their internal `current_user` lookups.
- Change `get_spotify_client_for_request`'s bare `except Exception` to catch only Spotify and network errors, and **log** them.
- If a worker needs the DB, wrap it in `with app.app_context():` as `refresh_user_library` already does.

### A4. Replace the per-visitor scheduler with one background job
Your comment at line 358 already describes the design: the home charts are **global**. They don't depend on who is logged in. So:
1. Run a single job (APScheduler `BackgroundScheduler`, or Windows Task Scheduler running `flask refresh-home` if you prefer no in-process thread) at 00:00 and, say, every 6 hours. It calls `build_home_snapshot()` and upserts **one** `HomeData` row (or inserts a row and deletes the older ones).
2. `home()` only reads that row. If none exists yet (first boot), run the build once in-process.
3. The per-user parts (featured artist album tracks, playlists) come from the cache (P6) or the lazy endpoint (P2), not from `HomeData`.
4. Delete `should_run_24h_task`, `number_of_run`, `SchedulerStatus`, `get_session_id`, `HomeData.user_id`, `loading_message`/`/app-status`, and the `new_time_tag` global.

With the debug reloader on, APScheduler starts twice. Guard it with `if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:`.

### A5. Turn song recognition into a proper background job
```
POST /jobs                  -> creates Job(id, user_id, playlist_id, status='queued'), files in uploads/<user>/<job>/
                               starts worker thread (or RQ/Celery later) -> returns {job_id}
GET  /jobs/<job_id>/status  -> JSON from Job row (owner-checked)
```
The worker updates the `Job` row (counts, last message, `completed`) instead of the global `STATUS`. The page polls `/jobs/<id>/status`, which `song_processing.html` already mostly does with `fetchStatus()`. Remove the `EventSource`. Replace the four log tables (`RecognisedSongs`, `UnrecognisedSongs`, `SentSpotifySongs`, `UnsentSpotifySongs`) with one `JobItem(job_id, filename, title, artist, stage, ok)` table. Store `title` and `artist` as **columns** instead of `"file::title::artist"` strings that get split back apart (line 3551). Delete the job's folder when it finishes.

### A6. Configuration and app factory
Read env vars once in `config.py`, check the required ones at startup, and remove the scattered `os.getenv` calls. Move `db.create_all()` out of import time. Add **Flask-Migrate** (Alembic) so schema changes don't need the commented-out `Table.drop()` lines (305-309), which lose data.

### A7. Small code quality fixes
- Remove the unused imports: `date` (duplicated), `unique`, `exception`, `title` (from dominate), `default_fill_value` (from numpy), `webbrowser`, `billboard`, `pprint`, `Bootstrap5`'s duplicates. Remove the repeated `import time/requests/json/asyncio`, and the `import json`/`import re` inside functions (lines 1298, 1394, 1802).
- Run `ruff check --select F,E,B,UP` once. It finds unused names, undefined names and many of the unbound-variable bugs above automatically.
- Remove the `default_id = 111111111` placeholder Spotify id (line 1562). Use `None` and have the template hide the button.
- `extract_main_artist` (line 1539) splits on the substring `and`, so "Brandy" becomes "Br" and "Sandé" becomes "S". Use `\band\b`.
- `MUSIC_FOLDER`, `MUSIC_FOLDER_2`, `SUCCESS_LOG` and `FAILED_LOG` (lines 3341-3345) are unused.
- `/elements` (line 3269) is the template's demo page. Remove it, as the comment above it says.
- Escape user input in URLs: lines 2124, 2264, 2366, 2600 and 3191 build query strings with f-strings, so an artist like "Simon & Garfunkel" breaks the request. Use `params={...}`.
- Spotify API changes: if your Spotify app was registered **after 27 Nov 2024**, `artist_related_artists` (line 2291), `recommendations`, and Spotify-owned editorial playlists such as `this_weeks_hits_id = "37i9dQZF1DXcBWIGoYBM5M"` (line 103) return 403/404, and `preview_url` is usually `null`. Check your app in the Spotify dashboard and remove those features, or replace them with Last.fm `artist.getSimilar`.

---

## 6. Templates and front-end

### F1. Use one base template
None of the 37 templates uses `{% extends %}`. Each one includes `header.html`/`footer.html` and then **pastes in the same scripts**: the add-to-playlist modal and its `fetch('/add_to_playlist')` handler (13 templates), and the "Calibrating…" dots and loading-overlay script (about 25). Create `base.html` with `{% block content %}` and `{% block scripts %}`, and move the shared JS into `static/js/playlist-modal.js` and `static/js/loader.js`. A fix to the modal then happens in one place instead of 13.

### F2. Remove dead or demo templates
Check whether these are still reachable: `elements.html` (1,149 lines of template demo), `test-dropzone.html`, `pop-up-playlist.html`, `selected-playlist.html`, `initial_loader.html`, `remember_this_4_index` (no extension). Delete the ones nothing renders. To check:
```powershell
Select-String -Path one-music-gh-pages\main.py -Pattern "render_template\('([^']+)'" | % { $_.Matches.Groups[1].Value } | Sort-Object -Unique
```
Compare that list to `templates/` (remember the `{% include %}`s).

### F3. Accessibility and UX
- Many `<img>` tags have `alt=""`, including the logo. Give meaningful images real alt text.
- The loading overlay depends on `#loading-state` text being `'True'`/`'False'`. Use a `data-loading` attribute instead.
- Pass Jinja values to JS with `{{ value | tojson }}` instead of `"{{ playlist_id }}"`.

---

## 7. Testing

There are no tests, and `test.py` is not one. Start small and focus on the code most likely to break:

### T1. Set up pytest
```powershell
.venv\Scripts\pip install pytest pytest-mock responses
```
`tests/conftest.py` builds the app with `create_app("testing")` (once A1 exists) using `sqlite:///:memory:`, `WTF_CSRF_ENABLED=False` and a fake `sp`.

### T2. First tests: pure functions (no network)
- `billboard_scraper`'s artist normalisation: `"Alex Warren"` stays `"Alex Warren"` (B2), and `"A x B"` becomes `"A, B"`.
- `extract_main_artist("Brandy & Monica")` returns `"Brandy"` (A7).
- `get_artwork_url`, `format_artists`, `_parse_release_date`, `allowed_file`.
- Run the scrapers against **saved HTML fixtures** (`tests/fixtures/billboard_hot100.html`), so a Billboard layout change shows up as a fixture diff, not a production 500.

### T3. Route smoke tests (network mocked)
For each route, as both an anonymous and a logged-in user, assert `status_code in (200, 302)`. This catches B9, B10, B16 and B19. Mock `requests` with `responses` and Spotify with a `MagicMock`.

### T4. Regression tests for the bugs above
Add one test for each B-item you fix. Write it so it fails before the fix and passes after, and include it in the same commit.

### T5. Continuous integration
Add `.github/workflows/ci.yml` that runs `ruff check` and `pytest` on push. It takes about 15 lines.

---

## 8. Using Claude Code and subagents to go faster

Subagents are separate Claude workers. Each starts with a fresh context, does one job, and reports back. They speed up **independent** work. They cause problems when two of them edit the same file. Because everything currently lives in one 3,726-line `main.py`, **finish Phase 1 to 3 below one step at a time, and do the A1 split before you hand out parallel edit work.**

### 8.1 When to use which

| Task | Tool | Why |
|---|---|---|
| "Find every place that does X" (all `requests.get` without timeout, every `return None` view) | **Explore** subagent | Read-only. It searches widely and returns only the list, so your main conversation stays small. |
| Designing A1/A4/A5 before writing code | **Plan** subagent | Returns a step-by-step plan and the files involved, without editing. |
| Independent edits that touch different files (after A1) | **general-purpose** subagents with `isolation: "worktree"` | Each gets its own git worktree and branch, so they can't overwrite each other. You merge the results. |
| Reviewing a finished branch | `/code-review` (skill) | Checks the diff for correctness bugs before you merge. `/security-review` covers S1 to S8. |
| Repeated cleanup passes | `/simplify` | Cleans up the code you just changed. |

### 8.2 Prompts you can paste

**Audit fan-out (read-only, safe to run all three at once).** In one message:
> Use 3 Explore subagents in parallel on `one-music-gh-pages/`:
> 1. List every `requests.get/post` call in main.py with its line number, URL, and whether it has `timeout=` and uses `params=` (vs f-string URL).
> 2. List every route and, for each, whether it has `@login_required`, every attribute of `current_user` it reads, and every `return None`.
> 3. List every template under `templates/`, whether any `render_template` or `{% include %}` references it, and which ones contain the add-to-playlist modal JS.
> Return tables only.

**Plan the split before doing it:**
> Use a Plan subagent: read `one-music-gh-pages/main.py` and `improvement-guide.md` §5 A1. Produce an ordered move list (function → target module), the import graph between new modules, and every `url_for('x')` in templates that must change to `url_for('bp.x')`. No edits.

**Parallel implementation after A1 (worktrees):**
> Spawn 3 general-purpose subagents, each with `isolation: "worktree"`, on top of the branch `refactor/split-main`:
> - Agent A: implement P1 + P2 in `app/services/spotify.py` and `blueprints/library.py` only. Add tests in `tests/test_spotify_service.py`.
> - Agent B: implement S1 + S2 (nh3 sanitising, CSRFProtect + tokens in every form and fetch). Touch only `blueprints/news.py`, `blueprints/auth.py`, `extensions.py`, templates.
> - Agent C: implement A4 in `app/tasks.py` and `services/home_feed.py`; remove scheduler code from `blueprints/main.py`.
> Each agent: run `pytest` before finishing and report the branch name and a summary of what changed.

Then merge each worktree branch on its own and run `/code-review` on each before merging.

**Fixing a batch of small bugs (one agent, sequential, not parallel):**
> Fix B1, B2, B3, B4, B5 from improvement-guide.md. One commit per item with message `fix(Bn): …`. Add a pytest regression test for B2 and B3.

### 8.3 Rules that keep agent work safe
1. **One file, one writer at a time.** Never give two parallel agents the same file. Split `main.py` first.
2. **Give each agent a clear end condition.** "Run `pytest -q` and `ruff check`, both must pass" beats "make it better".
3. **Check what comes back.** An agent's report is a summary, so read the diff (`git diff main...<branch>`) before merging.
4. **Keep secrets out of prompts.** Agents can read `.env` if you ask them to, so don't. Point them at `.env.example`.
5. **Write the project rules down once** in `CLAUDE.md` (R6), so every new session and subagent picks them up automatically.
6. **Use `/fewer-permission-prompts`** after a few sessions, so read-only commands (`git status`, `pytest`, `ruff`) stop asking for approval.

---

## 9. Suggested roadmap

Each phase leaves the app working. Commit after every item.

### Phase 0: repository cleanup (≈1 hour)
R1 → R2 → commit the current uncommitted `main.py` change → R4 (fix the bootstrap package conflict and add `requirements.txt` + `.env.example`) → R5 → R6.

### Phase 1: small fixes users will notice (≈half a day)
B1, B2, B3, B4, B5, B11, B13, B15, B16, B22, plus B21's two one-line fixes. Each is a change of under 10 lines.

### Phase 2: stop the 500 errors (≈1 day)
B9 (replace the 29 `return None`s), B10 (`@login_required` + `login_view`), B6 (safe future results), B8, B17, B18, B19, B20, B23, B24. Add T1 and T3 smoke tests as you go. This phase gets the most out of tests.

### Phase 3: security (≈half a day)
S1, S2, S3, S4, S5, S6, S7. Then run `/security-review`.

### Phase 4: speed (≈1 day)
P1 (the biggest win), P5, P3, P4, P7, P9, P10, R3 (the images). Measure before and after with the browser's Network tab, or by timing `requests.get('http://127.0.0.1:5000/playlist')` from a logged-in session.

### Phase 5: restructure (≈2 to 3 days, use subagents here)
A1 (move code without changing behaviour), then A2 and A3, then use worktree agents in parallel for A4, A5, P2, P6 and F1. Then A6 (Flask-Migrate) and T5 (CI).

### Phase 6: nice to have
P11 (WAL, indexes, snapshot-based sync), S8 (rate limiting), F2, F3, A7 cleanups, and checking the Spotify API changes (A7, last bullet).

---

### Quick reference: highest-value changes

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | P1: use the playlist listing data, stop fetching every playlist | 20 min | Every logged-in page gets much faster |
| 2 | B3: playlist-image crash | 2 min | Pages stop crashing for users with cover-less playlists |
| 3 | S1: clean comment HTML | 20 min | Closes a stored-XSS hole |
| 4 | B9 + B10: no more `return None` or anonymous crashes | 1 h | No more 500 errors |
| 5 | A4: one scheduled home refresh | 2 to 3 h | Fast home page, and removes the fragile scheduler |
| 6 | B1 + B2: Billboard date and "x" bugs | 5 min | "See what's new" shows correct results |
| 7 | R3: compress images | 30 min | First load drops from about 40 MB to about 2 MB |
