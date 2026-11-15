# SSPIDERR: a beginner's guide to the app and what changed

This document explains **what SSPIDERR is, how it works, and what changed** between the version you wrote and the version on the `claude-test` branch. It focuses on the `SSPIDERR-APP/` folder.

It is written for someone new to web development. Technical words are explained the first time they appear. Each part answers three questions:

1. **What does this part do?**
2. **How did the old version do it?**
3. **What changed, and why is that better?**

---

## Contents

1. [What SSPIDERR is](#1-what-sspiderr-is)
2. [A 5-minute crash course: how a web app works](#2-a-5-minute-crash-course-how-a-web-app-works)
3. [The big picture: before and after](#3-the-big-picture-before-and-after)
4. [A tour of the SSPIDERR-APP folder](#4-a-tour-of-the-sspiderr-app-folder)
5. [How each feature works now](#5-how-each-feature-works-now)
6. [The improvements, one by one](#6-the-improvements-one-by-one)
7. [The database: what changed](#7-the-database-what-changed)
8. [The look and feel (UI/UX)](#8-the-look-and-feel-uiux)
9. [Tests: how we know it works](#9-tests-how-we-know-it-works)
10. [How to run it](#10-how-to-run-it)
11. [Glossary](#11-glossary)

---

## 1. What SSPIDERR is

SSPIDERR is a **music-discovery website**. It does three main things:

- **Shows what's popular right now.** It pulls in the top albums, songs and artists from Apple Music, Billboard, Last.fm, Deezer and Audiomack (for Afrobeats), plus GRAMMY winners and music news.
- **Connects to your Spotify account.** Any song you find on the site can be added to one of your Spotify playlists with one click, and you can create new playlists.
- **Turns your own music files into a Spotify playlist.** You upload MP3s (or other audio files) and the app listens to each one using **Shazam** (the song-recognition service). It works out the song and artist, finds the song on Spotify, and adds it to the playlist you chose.

It is built with **Python** and **Flask**, and the design uses the free "One Music" template by Colorlib.

---

## 2. A 5-minute crash course: how a web app works

If you already know this, skip to section 3.

When you open `http://127.0.0.1:5000/` in a browser, this happens:

```
 Your browser                     The SSPIDERR server (Python / Flask)
 ───────────                      ─────────────────────────────────────
 "Give me the page at /"  ──────▶  1. Flask finds the function for "/"  (a "route")
                                   2. That function gets data
                                      - from the database (saved data), or
                                      - from other websites' APIs (Spotify, Billboard...)
                                   3. It fills an HTML "template" with that data
 Shows the page  ◀──────────────   4. It sends the finished HTML back
```

The main building blocks:

| Word | What it means in SSPIDERR |
|---|---|
| **Route** | A Python function connected to a web address. For example, `/news-blog` runs the function that builds the news page. |
| **Template** | An HTML file with blanks such as `{{ song_name }}` that Python fills in. They live in `templates/`. |
| **Database** | A file (`instance/my_songs.db`) that remembers things between visits: users, comments, news, playlists. |
| **API** | Another website's "door" for programs. SSPIDERR asks the Spotify API "what are this user's playlists?" and gets data back. |
| **Static files** | Files sent as they are: CSS (styling), JavaScript (browser code) and images. They live in `static/`. |

The most important lesson behind many of the changes is this:

> **Every call to another website takes time: often 0.3 to 3 seconds, and sometimes 20 seconds if that site is slow.** If a page makes 100 such calls one after another before showing anything, the visitor waits minutes. A lot of the work below is about making fewer calls, making them in parallel, remembering (caching) the answers, and moving slow work into the background.

---

## 3. The big picture: before and after

| | Your version | Now |
|---|---|---|
| Python code | One file, `main.py`, with **3,726 lines** holding everything | **24 small files** in `app/`, each with one job (largest 438 lines) |
| Folder name | `one-music-gh-pages` | `SSPIDERR-APP` |
| Home page speed | Waited for every API on each refresh, which could take minutes | Shows saved data **instantly** (about 0.02 s); data refreshes in the background |
| `should_run_24h_task()` | One counter shared by every visitor, so it "worked for now" and then broke | Reliable: one shared refresh at midnight, plus automatic catch-up |
| Pages that could crash | Many: 29 places returned "nothing", which shows an error page | Every page renders; friendly error pages instead of crashes |
| Security | Comments could run JavaScript; forms had no protection; open redirects; debug mode on | All fixed (section 6.4) |
| Song uploads | One shared folder for all users; one shared progress tracker | Each user has their own folder and their own job with live progress |
| Images | `static/` was about **126 MB** (one image was 19 MB) | About **15 MB** |
| Database changes | Done by hand (commented-out `drop()` lines) | Proper migrations (versioned, safe, reversible) |
| Tests | None (`test.py` was an experiment file) | **199 automated tests** + automatic checks on GitHub |
| Look and feel | Every page copied the header, scripts and modal; a full-screen loader hid every page | One shared layout, consistent design, faster pages, clearer flows |

All of this is spread over a series of small commits on the `claude-test` branch, so every step can be reviewed or undone.

---

## 4. A tour of the SSPIDERR-APP folder

```
SSPIDERR-APP/
│
├── main.py              ← Start the app for development:  python main.py
├── serve.py             ← Start the app "for real" with the waitress server
├── requirements.txt     ← The list of Python packages the app needs (with exact versions)
├── requirements-dev.txt ← Extra tools for development (tests, linter, image tools)
├── .env                 ← YOUR secret keys (never shared, never committed)
├── .env.example         ← A blank copy of .env that shows which keys are needed
├── pytest.ini, ruff.toml← Settings for the test runner and the code checker
│
├── app/                 ← ALL the Python code
│   ├── __init__.py      ← create_app(): assembles the app (settings, database, routes, error pages)
│   ├── config.py        ← Reads every setting from .env in ONE place
│   ├── extensions.py    ← The Flask add-ons (database, login, CSRF, cache, rate limiter...)
│   ├── models.py        ← Describes the database tables as Python classes
│   ├── tasks.py         ← Background jobs + should_run_24h_task()
│   ├── utils.py         ← Small helpers (safe redirects, "Spotify required" check)
│   │
│   ├── blueprints/      ← The ROUTES (web addresses), grouped by topic
│   │   ├── main.py      ← Home, About, Contact, US Top 40, Time Travel, Suggestions, GRAMMYs
│   │   ├── auth.py      ← Log in, register, log out, connect Spotify
│   │   ├── music.py     ← Song, album, artist, Afrobeats, Billboard charts pages
│   │   ├── library.py   ← Your playlists, create playlist, "add to playlist"
│   │   ├── news.py      ← News list, article page, comments (post / edit / delete)
│   │   └── uploads.py   ← Upload songs, choose playlist, processing progress
│   │
│   ├── services/        ← The "workers" that do the real work (no web pages here)
│   │   ├── http.py         ← One shared connection to the internet (timeouts + retries)
│   │   ├── spotify.py      ← Spotify login tokens, playlists, tracks
│   │   ├── catalog.py      ← Song/artist/album lookups (Spotify, iTunes, Last.fm, Deezer)
│   │   ├── scrapers.py     ← Reads Billboard and Audiomack chart pages
│   │   ├── charts.py       ← Builds chart pages, GRAMMY winners, suggestions
│   │   ├── home_feed.py    ← Builds the home page data
│   │   ├── news.py         ← Downloads and stores music news
│   │   ├── uploads.py      ← The upload → recognise → add-to-Spotify pipeline
│   │   ├── concurrency.py  ← Runs several lookups at the same time, safely
│   │   └── sanitize.py     ← Cleans HTML so nobody can inject harmful code
│   │
│   └── data/chart_sections.json ← The list of Billboard charts shown on "See what's new"
│
├── templates/           ← The HTML pages
│   ├── base.html        ← The shared layout every page is built on
│   ├── header.html, footer.html
│   ├── macros.html      ← Reusable pieces (track row, play button, add button...)
│   ├── partials/        ← Page fragments (chart results, contact form, upload steps)
│   └── index.html, song.html, artist.html, blog_post.html, ... (one per page)
│
├── static/              ← CSS, JavaScript and images
│   ├── css/style.css    ← The original One Music theme
│   ├── css/sspiderr.css ← NEW: SSPIDERR's own components (buttons, cards, modal...)
│   ├── js/app.js        ← NEW: shared browser code (playlist picker, previews, notifications)
│   └── img/             ← Images (now compressed)
│
├── migrations/          ← Database version history (Flask-Migrate)
├── tests/               ← 199 automated tests
└── instance/            ← Private data: the database, uploads in progress, cache (never committed)
```

### Why split one big file into many?

Picture a 3,726-page notebook with recipes, phone numbers, homework and shopping lists all mixed together. Finding anything is slow, and changing one thing can break another without you noticing. Splitting it into labelled folders means:

- You know **where to look**: playlist problem → `library.py` and `spotify.py`.
- Each file is **short enough to read** in one sitting.
- The **web pages** (blueprints) are separated from the **work** (services). The same "find this song on Spotify" code is written once and used by the home page, the chart pages and the upload pipeline.

---

## 5. How each feature works now

### 5.1 The home page and `should_run_24h_task()`

**What it shows:** the hottest album, song and artist (a sliding banner), the top albums, the global top 10, the year's best hits, popular artists and a featured artist.

**How the old version worked:** each visit called `should_run_24h_task(current_user_id)`. If it said "yes", the page fetched everything from about seven APIs before showing anything. The function used a global counter, `number_of_run`, shared by everyone:

```python
# OLD (main.py)
number_of_run=1
def should_run_24h_task(current_user_id):
    global number_of_run ## keeps track of the number of runs
    ...
    if current_user_id:
        if number_of_run==1:
            status = SchedulerStatus.query.filter_by(user_id=current_user_id)...
```

Problems with that:
- The first visitor after a restart changed the counter **for everybody**.
- Data was saved separately per visitor, even though the charts are the same for everyone.
- Your own code comment pointed at the next problem: *"If a user is constantly on this app does it mean there will be no updates?"*
- The timestamp `new_time_tag` was set **once, when the server started**, so every saved row had the same time.

**How it works now** (`app/tasks.py`):

1. The home data is **global**: one snapshot for everyone, stored in the `home_data` table.
2. A **scheduler** (APScheduler) runs inside the app:
   - at **00:00 every day**, it refreshes the home data;
   - every **30 minutes**, it checks whether a refresh was missed, for example because the computer was asleep at midnight.
3. `should_run_24h_task()` answers one question: **is the saved data stale?**

```python
# NEW (app/tasks.py), simplified
def should_run_24h_task(job_name=HOME_JOB, now=None, ...):
    status = (the job's row in scheduler_status)
    if status is None:                       return True   # never ran
    if it is running right now:              return False  # don't start twice
    if it failed less than 15 minutes ago:   return False  # don't hammer a broken API
    if it never succeeded:                   return True
    if last success is 24+ hours old:        return True
    return last success was on an earlier calendar day      # the "midnight" rule
```

4. When you open the home page, `home()` **only reads the database**, so it's instant. If the data is stale, it starts a refresh **in the background** and still shows the current data immediately.
5. Only on the very first run ever, when there's no data at all, does the page wait while the data is built.

You can choose the timezone for "midnight" with `SCHEDULER_TIMEZONE=Africa/Lagos` in `.env`.

### 5.2 Discovering music (charts)

- **See what's new** (`/see-whats-new`): Billboard charts (Hot 100, Billboard 200, Artist 100, 52 country charts, "Greatest of all time" and Pop charts). Pick a chart and, optionally, a past week. Results load without reloading the page.
- **US Top 40**, **Time Travel** (any week since 1958), **Suggestions** (songs by artists similar to the ones in your playlists, using Last.fm) and **GRAMMY winners** (by year). In the old version these four were **empty pages that only said "Title"**, or (the awards page) **crashed**.
- **Afrobeats** (`/afro-beats`): the Audiomack charts, matched to Spotify.

Each chart row shows the cover, the title, the artist (linked to their page), a **play button** for a 30-second preview, and an **Add** button that adds the song to a Spotify playlist.

### 5.3 Song, album and artist pages

Each page shows a big header with artwork, stats (listeners, plays, popularity), a description from Last.fm, and track lists with play and Add buttons. They work for **iTunes, Deezer and Spotify IDs**, because the home page uses all three. If an item can't be found, you get a friendly "Not found" page instead of a crash.

### 5.4 Your Spotify account and playlists

- **Connecting Spotify:** after registering, a clear page explains why Spotify access is needed. Then the usual Spotify "Allow" screen appears. Your login tokens (keys that let SSPIDERR act for you) are saved on your user row and **refreshed only when they are about to expire**.
- **Playlists page** (`/playlist`): all your playlists, plus new album releases.
- **"Add to playlist" anywhere:** press **Add** next to any song and one shared pop-up lists the playlists you're allowed to add to. These load **only when you open the pop-up** and are remembered for 5 minutes.

### 5.5 Uploading your own songs (the 3-step flow)

1. **Upload** (`/loader-page`): drag files in. They're saved in **your own private folder** (`instance/uploads/<your id>/`). You can remove files before continuing.
2. **Choose a playlist** (`/display-uploads`): pick one of your playlists or create a new one.
3. **Processing** (`/song-processing/...`): a **background job** starts:
   - Shazam recognises each song, one every 3 seconds to respect Shazam's limits;
   - each song is searched on Spotify;
   - songs **already in the playlist are skipped** and labelled "Already in playlist";
   - the rest are added in batches of up to 100.

   The page shows a progress bar, five counters (Recognised, Not recognised, Added, Already in playlist, Not on Spotify) and, at the end, a song-by-song table.

**What happens to your files:** they're **deleted as soon as the job finishes**. Uploads you never processed are deleted after 24 hours. The per-song results are kept for **30 days** (setting `UPLOAD_RESULTS_RETENTION_DAYS`) and then removed automatically.

### 5.6 News and comments

- **News list** (`/news-blog`): articles from NewsData.io and Billboard, refreshed in the background. The newest 150 are kept, and posts with comments are never deleted.
- **Article page** (`/blog-post/<id>`): a professional layout with the cover image, author, date, reading time, tags, a short excerpt with a "Read the full story" link to the original, share buttons, previous/next links and a "More news" sidebar.
- **Comments:** a clean comment box with a character counter, times like "3 hours ago", "You" and "edited" labels, **edit and delete for your own comments**, newest/oldest sorting, and a jump to your comment after you post it.

### 5.7 About, Contact, reviews

- **About** has six sections plus **reviews**. You must be logged in to leave one.
- **Contact** sends you an email. If email sending fails, the visitor sees a polite message instead of a crash, and the recipient address is now a setting rather than being written in the code.

---

## 6. The improvements, one by one

Here are the most important changes, grouped by type. Each one compares **your version** with **now**.

### 6.1 Bugs that are fixed

| # | The problem in your version | Now |
|---|---|---|
| 1 | **Previews never played.** The home page used the iTunes *web page* address as the audio source, and other pages played one dummy MP3. | Real 30-second previews (iTunes `previewUrl`). |
| 2 | **Opening a page downloaded songs.** (Reported by you after the first rewrite.) Each track row had an `<audio>` player, so browsers and download managers fetched or grabbed the songs on page load. | Pages contain only small **play buttons**. Nothing downloads until you press play. |
| 3 | **Crash for playlists without a cover image.** The code treated an image link (text) as a list. | Cover-less playlists show a neat placeholder. |
| 4 | **The letter "x" became a comma** in Billboard artist names ("Alex Warren" → "Ale, Warren"). | Only a standalone "x" between two names separates them. |
| 5 | **The chart date picker did nothing.** The page's JavaScript never sent the date. | The date is sent and understood in both formats. |
| 6 | **One broken API broke the whole home page.** | Each source can fail on its own; the page still works. |
| 7 | **29 places returned "nothing"** (`return None`), which Flask shows as a 500 error page. | They redirect to login or "connect Spotify", or show a friendly page. |
| 8 | **Logged-out visitors crashed** several pages, such as `/playlist` and `/display-uploads`. | Those pages ask you to log in first. |
| 9 | **A deleted account's cookie caused "404" on every page.** | You are simply logged out. |
| 10 | **News excerpts were always empty** (the template read a field that doesn't exist). | Excerpts show. |
| 11 | **News could crash** on articles without a date, or when the database was empty. | Fixed. |
| 12 | **14 of the 74 chart options** pointed to Billboard pages that don't exist (misspellings such as "malasia" and "neitherlands"). | All checked against Billboard and corrected. |
| 13 | **The About page's contact form** sent nowhere (`action="#"`). | It works. |
| 14 | **The playlist page showed a made-up "5 Awards Won".** | Real numbers: songs, average popularity, total length. |
| 15 | **Old cleanup deleted news posts but left their comments behind**, so 6 comments point at deleted posts. | Posts with comments are never deleted now. |
| 16 | **Spotify removed the "related artists" feature** for apps like yours, so the old code failed silently. | "Fans also like" now uses Last.fm's similar-artists data. |
| 17 | **Billboard glues names together** ("FeaturingLana Del Rey"). | Names are split correctly. |

### 6.2 The upload pipeline (a complete redesign)

| Your version | Now |
|---|---|
| Everyone uploaded into the **same folder** (`static/uploads`). | Each user has a **private folder** outside `static/`, so nobody can download anyone else's files. |
| **Every visit to the home page deleted that folder**, so one user's visit could wipe another user's upload in progress. | Folders are only cleaned by a scheduled job, and only old files. |
| Progress was one global `STATUS` dictionary, so all users saw each other's progress. | Each run is an **`UploadJob`** row with its own progress. |
| Processing ran **inside the web request** for minutes, started through `EventSource`, which reconnects by itself, so **the whole job could run twice and add duplicates**. | Processing runs in a **background thread**. Reloading the page resumes watching; it never restarts the job. |
| Results were stored as `"file::title::artist"` text in four separate tables. | One `upload_job_items` table with proper columns. |
| Duplicates showed as "Added". | They show as **"Already in playlist"** and have their own counter. |

### 6.3 Speed

| Your version | Now |
|---|---|
| Listing playlists made **about 3 Spotify calls per playlist** (one to fetch each playlist, plus a full download of its tracks just to count them). A user with 30 playlists meant about 100 calls on **every page** with the playlist pop-up. | **One call per 50 playlists**, using data Spotify already returns. The list loads only when the pop-up opens, and is remembered for 5 minutes. |
| The artist page looked up the *same* artist image again for every track, fetched every album the artist ever released, and ran 20 extra lookups for related artists that weren't even shown. | One image lookup, only the newest 4 releases, and similar artists shown with their photos. |
| Most internet requests had **no time limit**, so one slow website could freeze a page forever. | Every request has a time limit and sensible retries (`services/http.py`). |
| Nothing was remembered between visits. | Lookups such as artist images and chart pages are **cached**, so a second visit is almost instant. |
| News was downloaded **when the app started**, and old news was deleted **on every visit** to the news page. | Both happen in the background scheduler. |
| 119 `print()` lines, some printing about 100 KB of data per visit. | Proper logging with levels; no secrets in logs. |
| **126 MB of images** (one was 19 MB). | **15 MB**: unused images removed, the rest compressed. |
| Several stylesheets and scripts loaded twice, for example a second copy of Bootstrap on the charts page. | One shared layout loads each file once. |

Measured on the real app: the home page now loads in **about 0.02 s**. Chart and artist pages take a few seconds the first time (they gather data from several sites) and are near-instant afterwards.

### 6.4 Security

| Risk in your version | What it means | Now |
|---|---|---|
| Comments were shown with `\| safe`. | **XSS**: anyone could post a comment containing JavaScript that runs for every reader (for example, to steal their login). | Comments are stored as plain text, and all outside HTML is cleaned with **nh3**. |
| Most forms had no CSRF token. | **CSRF**: another website could secretly submit forms (like "add to playlist") as you. | Every form and every background request carries a token. |
| `redirect(request.args.get('next'))` | **Open redirect**: a link could send users from your site to a fake one. | Only addresses on your own site are allowed. |
| `app.run(debug=True)` | Debug mode lets anyone who reaches the server run Python code on it. | Debug only when you set `FLASK_DEBUG=1`. |
| Weak password hashing (pbkdf2 with a short salt) | Stolen hashes are easier to crack. | Werkzeug's stronger default (scrypt). Old passwords still work. |
| Uploads had no login check and no size limit. | Anyone could fill your disk. | Login required, 50 MB per file, rate limited. |
| An unused Cloudinary URL was built from your secret, and your email address was written in the code. | Secrets and personal data in source code. | Removed; the email is now a setting. |
| No rate limits | Anyone could guess passwords or flood the contact form. | Limits on login, register, contact, comments and uploads. |
| (Found during testing) Failed requests wrote the **full address, including your API key**, into the log. | Logs are often shared when debugging. | Logs show only the page and the error code. |

### 6.5 How the code is organised

| Your version | Now | Why it matters |
|---|---|---|
| One 3,726-line file | Blueprints + services (section 4) | Easier to find, read and change. |
| The same 4-line "get Spotify token / return None" block copied into about 12 routes, and two nearly identical `render_template` calls per route | A `@spotify_required` decorator and one render per route | Less copy-paste, fewer places for bugs. |
| `current_user` passed into background threads, which fails there (silently, because errors were swallowed) | Threads receive plain values; one helper runs lookups in parallel safely | No hidden failures. |
| Settings read with `os.getenv` all over the file | All settings in `config.py` | One place to see and change them. |
| Unused imports (numpy, dominate, webbrowser...) and dead code | Removed | Faster start-up, less confusion. |
| Flask 2.2 with three conflicting "flask_bootstrap" packages installed | Flask 3.1 with one correct package | Predictable behaviour. |
| Flask-Gravatar (broken on Flask 3) | A 5-line `gravatar` filter | One less abandoned dependency. |
| CKEditor 4.22.1 (end-of-life; showed a "not secure" warning) | A simple, clean comment box | Looks professional, safer. |

---

## 7. The database: what changed

Your existing tables and data were **kept and reused**. Changes are applied by **migrations**: small, numbered scripts in `migrations/versions/` that upgrade the database step by step. You can always see which step the database is on with `flask --app main db current`.

| Migration | What it did |
|---|---|
| `0001_baseline` | A copy of your original tables, so the history starts from your version. |
| `0002_refactor` | Added the token-expiry time to users and the snapshot ID and indexes to playlists. Made `home_data` one global feed. Rebuilt `scheduler_status` as one row per job. Replaced the four recognition-log tables with `upload_jobs` and `upload_job_items`. |
| `0003` | Added the author name (`byline`) and `tags` to news posts, and `edited_at` to comments. |
| `0004` | Added `already_in_playlist` to upload results, and correctly relabelled your earlier "ALIVE" run. |

**Your data was kept:** users, comments, reviews, the 2,670 songs and the 45 playlists. Backups were made before each change, in `db-backups/`:

- `my_songs-2026-11-14-before-refactor.db` (your original database)
- `my_songs-2026-11-14-before-0003.db`
- `my_songs-2026-11-14-before-0004.db`

Two tables now have fewer rows **by design**: `blog_posts` keeps the newest 150 news posts (plus any with comments), and `home_data` keeps the 3 latest snapshots.

---

## 8. The look and feel (UI/UX)

**UI** is what you see; **UX** is how easy and pleasant the site is to use.

| Your version | Now |
|---|---|
| Each of 37 templates had its own copy of the header, scripts, playlist pop-up and loader code. | **One shared layout** (`base.html`) and reusable pieces (`macros.html`). A fix in one place fixes every page. |
| A full-screen loading screen hid **every page** until all images (up to 20 MB each) had downloaded. | Pages show immediately. |
| Pop-ups used `alert()` boxes. | Small, tidy **notifications** in the corner. |
| The "Add to playlist" button only appeared when logged in, and the pop-up was pre-filled on every page (slow). | One **Add** button everywhere. If you're logged out, it asks you to log in. The pop-up loads your playlists only when opened. |
| Audio players on every row (heavy, and they downloaded songs). | Small **play buttons** with a progress ring, one song at a time. |
| Empty sections were just blank. | Friendly **empty states** ("No comments yet. Be the first to say something."). |
| Crashes showed Flask's error page. | Branded **error pages** ("Page not found", "Spotify is having trouble"...). |
| Menu: "Elements" (a template demo page) and a fake shopping cart showing "1". | Clean menu: Home, Discover (with the chart pages), Playlists, Upload, News, About, Contact, plus "Connect Spotify" when needed. |
| Upload flow: unclear steps and an animated penguin background. | A clear **3-step flow** with live counters and a results table. |
| Article pages: a large image and a bare text area. | A **magazine-style article** with author, tags, reading time, sharing and related news. |
| Several images had no descriptions. | Images have `alt` text, forms have labels, and keyboard focus is visible (better for screen readers). |

The design still uses your **One Music** theme, so the site keeps its look; it is just more consistent and polished.

---

## 9. Tests: how we know it works

A **test** is a small program that uses the app and checks the result automatically. For example: "log in with the wrong password → the page must say *Incorrect email or password*".

There are **199 tests** in `tests/`. They cover:

- `test_scheduler.py`: `should_run_24h_task()` (midnight rule, timezones, 24-hour limit, "already running", back-off after failures)
- `test_routes.py`: every page, logged in and logged out; login, register, comments, editing, security checks
- `test_uploads.py`: the whole upload → recognise → add pipeline, privacy between users, the 30-day clean-up
- `test_spotify.py`: playlists, token refresh, odd Spotify data (local files, podcasts, missing images)
- `test_parsers.py`: Billboard/Audiomack/GRAMMY parsing and artist-name cleaning
- `test_feeds.py`: the home feed and the news feed

**No test uses the real internet.** Spotify, Shazam, Billboard and the rest are replaced by fakes, so the tests are fast and never touch your real Spotify account. A safety net makes any test fail immediately if it accidentally tries to go online.

The app was also run against the **real** APIs: every page returned successfully, and the home and news refreshes completed.

GitHub runs the tests and the code checker (**ruff**) automatically on every push (`.github/workflows/ci.yml`).

> **Still to try yourself:** the actions that change your real Spotify account (adding a song, creating a playlist, a full upload run) were tested with fakes only, to keep your account safe. Please try each once.

---

## 10. How to run it

In PowerShell:

```powershell
cd "C:\Users\pc\Downloads\SPIDER WEB APP\SSPIDERR-APP"

# first time only
..\.venv\Scripts\python -m pip install -r requirements-dev.txt
..\.venv\Scripts\flask --app main db upgrade        # brings the database up to date

# every day: development mode (auto-reloads when you edit code)
$env:FLASK_DEBUG = "1"; ..\.venv\Scripts\python main.py
# open http://127.0.0.1:5000

# "production" mode (more robust; one process, several threads)
..\.venv\Scripts\python serve.py

# run the tests
..\.venv\Scripts\python -m pytest
```

Useful settings in `.env` (see `.env.example` for all of them):

| Setting | Meaning |
|---|---|
| `SCHEDULER_TIMEZONE` | When "midnight" is for the daily refresh, for example `Africa/Lagos`. |
| `UPLOAD_RESULTS_RETENTION_DAYS` | How long upload results are kept (default 30; 0 = forever). |
| `CONTACT_RECIPIENT` | Where contact-form emails go. |
| `SCHEDULER_ENABLED` | Set to `0` to switch off background jobs. |

If you change `models.py` (the database design), create and apply a migration:

```powershell
..\.venv\Scripts\flask --app main db migrate -m "what changed"
..\.venv\Scripts\flask --app main db upgrade
```

---

## 11. Glossary

| Term | Plain-English meaning |
|---|---|
| **API** | A way for one program to ask another for data (for example, asking Spotify for your playlists). |
| **Background job / thread** | Work the server does "on the side" so a visitor doesn't have to wait for it. |
| **Blueprint** | A Flask feature for grouping related routes into their own file. |
| **Cache** | A short-term memory of answers so the app doesn't ask the same question twice. |
| **CSRF** | A trick where another site makes your browser submit a form on SSPIDERR without you knowing. Blocked by secret tokens in every form. |
| **Database migration** | A numbered script that changes the database structure safely and can be undone. |
| **Decorator** | A line like `@login_required` above a function that adds behaviour (here: "must be logged in"). |
| **Flask** | The Python framework SSPIDERR is built on. It connects web addresses to Python functions. |
| **Jinja2** | The template language used in the HTML files (`{{ ... }}` and `{% ... %}`). |
| **Rate limit** | A cap on how often someone can do something (for example, 10 login attempts a minute). |
| **Route** | A web address connected to a Python function. |
| **Scheduler** | A clock inside the app that runs jobs at set times (for example, the midnight refresh). |
| **Scraping** | Reading a website's HTML to pull out information (used for Billboard and Audiomack charts). |
| **Template** | An HTML page with blanks that Python fills in. |
| **Token** (Spotify) | A temporary key that lets SSPIDERR act for you on Spotify, refreshed automatically. |
| **XSS** | Getting harmful JavaScript to run on someone else's page, for example through a comment. Blocked by cleaning HTML. |

---

*For the detailed technical findings (with item IDs like B3, S1 and P1), see `improvement-guide.md`. For setup instructions, see `README.md`.*
