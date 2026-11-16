# CLAUDE.md

Guidance for Claude Code in this repository. It overrides `C:\Users\pc\Downloads\CLAUDE.md`, which describes an unrelated LangChain course.

## What this is

SSPIDERR, a Flask music-discovery app. All code is in `SSPIDERR-APP/`. See README.md for features and layout. `improvement-guide.md` lists the review findings (IDs like B3, S1, P1) and their status.

## Commands (run from `SSPIDERR-APP/`, PowerShell)

```powershell
..\.venv\Scripts\python -m pytest            # 180+ tests, no network
..\.venv\Scripts\ruff check .
$env:FLASK_DEBUG="1"; ..\.venv\Scripts\python main.py
..\.venv\Scripts\flask --app main db migrate -m "describe change"   # after editing models.py
..\.venv\Scripts\flask --app main db upgrade
```

The Python is 3.12 in `..\.venv`. Run tests with `SCHEDULER_ENABLED=0` set if you start the app in the same shell.

## Rules for this code base

- **Never pass `current_user`, `request`, `session` or `url_for` into threads.** Resolve them in the request and pass ids or a ready Spotify client. Use `services.concurrency.run_parallel` / `parallel_map`: they add an app context and turn failures into defaults.
- Public catalogue data uses `services.spotify.app_client()`. Only playlist operations use the user's client (`user_client()` or the `@spotify_required` decorator, which sets `g.sp`).
- Every outbound HTTP call goes through `services.http` (timeouts and retries). Never log full URLs, because they contain API keys.
- HTML from users or third parties is rendered with `| clean_html`, never `| safe`.
- Every form needs `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`, and `fetch` calls go through `SSPIDERR.fetch()` (static/js/app.js).
- Templates extend `base.html` and use `macros.html` (`track_row`, `add_button`, `img`, `empty`, `media_hero`). An element with `data-add-track="<spotify id>"` opens the shared playlist picker.
- The home feed is global. It is built by `tasks.run_job(HOME_JOB)`, and `should_run_24h_task()` decides when the data is stale. Don't fetch APIs inside `home()`.
- Schema changes go through Flask-Migrate. Never use `db.drop_all()` or drop tables by hand.
- Don't commit `.env`, `instance/` (DB, uploads, cache) or `db-backups/`.
- Commit messages: `<area>: <what changed>`.
