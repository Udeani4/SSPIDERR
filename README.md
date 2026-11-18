# SSPIDERR

A Flask music-discovery app. Browse what's hot (Billboard, Apple Music, Last.fm, Audiomack, GRAMMY winners), add any song to your Spotify playlists in one click, or upload your own music files and let SSPIDERR recognise them (Shazam) and build a Spotify playlist from them.

The app lives in [`SSPIDERR-APP/`](SSPIDERR-APP/) and is built on the Colorlib "One Music" template.

## Features

- **Home**: today's top album, song and artist, the global top 10, the year's best hits and popular artists. The data refreshes automatically once a day at midnight.
- **Discover**: live Billboard charts for the US and 60+ countries, any past week back to 1958, US Top 40, Afrobeats charts, GRAMMY winners and suggestions based on your playlists.
- **Song, album and artist pages** with stats, bios, previews and track lists.
- **Playlists**: see your Spotify playlists, create new ones and add songs from anywhere on the site.
- **Local songs to Spotify**: upload music files, then pick a playlist, then watch them being recognised and added.
- **News**: music news from NewsData.io and Billboard, with comments.

## Running it (Windows / PowerShell)

```powershell
cd SSPIDERR-APP
python -m venv ..\.venv                     # once
..\.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env                 # then fill in the keys
..\.venv\Scripts\flask --app main db upgrade
$env:FLASK_DEBUG = "1"; ..\.venv\Scripts\python main.py   # development, http://127.0.0.1:5000
..\.venv\Scripts\python serve.py                          # production (waitress)
```

Your Spotify app's Redirect URI (Spotify dashboard) must match `SSPIDERR_SPOTIFY_REDIRECT_URI`, e.g. `http://127.0.0.1:5000/callback`.

## Hosting on Render

`render.yaml` (repo root) is a Render Blueprint: it creates the web app and a free PostgreSQL database.

1. In Render: **New -> Blueprint**, pick this GitHub repository, and enter the values it asks for (copy them from `SSPIDERR-APP/.env`).
2. In the Spotify Developer Dashboard, add `https://<your-service>.onrender.com/callback` as a Redirect URI and use the same value for `SSPIDERR_SPOTIFY_REDIRECT_URI`.
3. Pushing to `main` redeploys automatically.

Free plan: the app sleeps after 15 idle minutes (about a minute to wake), and the free database expires after 30 days unless upgraded.

## Tests

```powershell
cd SSPIDERR-APP
..\.venv\Scripts\python -m pytest     # no network needed: every external API is faked
..\.venv\Scripts\ruff check .
```

GitHub Actions runs both on every push (`.github/workflows/ci.yml`).

## Screenshots for the About pages

The screenshots in `SSPIDERR-APP/static/img/about/` are generated from a private demo copy of the app (demo user and sample playlists, never your real Spotify account):

```powershell
cd SSPIDERR-APP
..\.venv\Scripts\python -m playwright install chromium   # once
..\.venv\Scripts\python tools\screenshots\capture.py     # all screenshots, or name some: capture.py charts song
```

The About page text lives in `SSPIDERR-APP/app/data/about.py`.

## Project layout

```
SSPIDERR-APP/
  app/
    __init__.py      create_app(): config, extensions, blueprints, error pages
    config.py        every environment variable, read once
    models.py        database models (schema changes go through migrations/)
    tasks.py         background jobs + should_run_24h_task()
    blueprints/      routes: main, auth, music, library, news, uploads
    services/        Spotify, catalogue (iTunes/Last.fm/Deezer), scrapers, charts,
                     news, home feed, uploads/recognition, shared HTTP session
  templates/         base.html + macros.html + one template per page
  static/            theme CSS/JS, sspiderr.css, app.js, images
  migrations/        Flask-Migrate (Alembic) revisions
  tests/             pytest suite
  main.py / serve.py development / production entry points
```

## External services

Spotify Web API, Shazam (via shazamio), Apple Music RSS and iTunes Search, Last.fm, Deezer, Billboard (scraped), Audiomack (scraped), grammy.com (scraped), NewsData.io and Google Custom Search (optional).
