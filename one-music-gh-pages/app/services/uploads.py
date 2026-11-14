"""Upload -> recognise (Shazam) -> add to Spotify playlist, as a background job (A5).

Files live in   instance/uploads/<user_id>/pending/          (before a job)
and move to     instance/uploads/<user_id>/jobs/<job_id>/    (while processing)

Each user has their own folder and each run is an UploadJob row, so users
never see or delete each other's uploads or progress (B21). The page polls
/jobs/<id>/status instead of holding a request open for minutes.
"""
import asyncio
import logging
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import spotipy
from flask import current_app
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import UploadJob, UploadJobItem, User, utcnow
from . import catalog
from .spotify import get_playlist_tracks, user_client

log = logging.getLogger(__name__)

EVENT_KEYS = {
    "recognized": "recognized",
    "not_recognized": "not_recognized",
    "sent": "sent_to_spotify",
    "not_sent": "not_sent_to_spotify",
}


# --------------------------------------------------------------------------
# Folders
# --------------------------------------------------------------------------
def upload_root():
    return Path(current_app.instance_path) / "uploads"


def pending_dir(user_id, create=True):
    path = upload_root() / str(int(user_id)) / "pending"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def job_dir(user_id, public_id):
    return upload_root() / str(int(user_id)) / "jobs" / public_id


def allowed_file(filename):
    return Path(filename).suffix.lower() in current_app.config["UPLOAD_EXTENSIONS"]


def list_pending(user_id):
    folder = pending_dir(user_id, create=False)
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and allowed_file(p.name))


def save_upload(user_id, storage):
    """Save one uploaded file. Returns (ok, message, filename)."""
    original = storage.filename or ""
    filename = secure_filename(original)
    if not filename or not Path(filename).stem:
        return False, "That file name isn't valid.", None
    if Path(filename).suffix.lower() == ".zip":
        return False, "ZIP files aren't supported. Upload the music files themselves.", None
    if not allowed_file(filename):
        allowed = ", ".join(sorted(current_app.config["UPLOAD_EXTENSIONS"]))
        return False, f"{filename} isn't a supported format ({allowed}).", None

    folder = pending_dir(user_id)
    target = folder / filename
    counter = 1
    while target.exists():                       # don't overwrite an earlier upload
        target = folder / f"{Path(filename).stem}-{counter}{Path(filename).suffix}"
        counter += 1
    storage.save(target)
    return True, "Uploaded", target.name


def delete_pending(user_id, filename):
    target = pending_dir(user_id, create=False) / secure_filename(filename)
    if target.is_file():
        target.unlink()
        return True
    return False


def cleanup_old_files(max_age_hours=24):
    """Scheduler job: remove stale pending uploads and leftover job folders."""
    root = upload_root()
    if not root.is_dir():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for path in root.glob("*/pending/*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    for path in root.glob("*/jobs/*"):
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
class JobError(Exception):
    pass


def active_job(user_id):
    return (UploadJob.query.filter(UploadJob.user_id == user_id, UploadJob.state.in_(("queued", "running")))
            .order_by(UploadJob.id.desc()).first())


def create_job(user, playlist_id, playlist_name=None):
    """Move the user's pending files into a new job. Returns (job, created).

    If the user already has a job running, that job is returned instead, so
    reloading the page can never start the same work twice.
    """
    running = active_job(user.id)
    if running:
        return running, False

    files = list_pending(user.id)
    if not files:
        raise JobError("There are no uploaded songs to process. Upload some songs first.")

    public_id = str(uuid.uuid4())
    target = job_dir(user.id, public_id)
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        shutil.move(str(pending_dir(user.id) / name), str(target / name))

    job = UploadJob(public_id=public_id, user_id=user.id, playlist_id=playlist_id,
                    playlist_name=playlist_name, state="queued", total_files=len(files),
                    processed_files=0, message="Waiting to start...")
    for name in files:
        job.items.append(UploadJobItem(filename=name))
    db.session.add(job)
    db.session.commit()
    return job, True


def start_job(job):
    app = current_app._get_current_object()
    thread = threading.Thread(target=process_job, args=(app, job.id), name=f"upload-job-{job.public_id}",
                              daemon=True)
    thread.start()
    return thread


def _update(job, *, message=None, event=None, event_text=None, **fields):
    if message is not None:
        job.message = message
    if event is not None:
        job.last_event = event
        job.last_event_text = (event_text or "")[:200]
    for key, value in fields.items():
        setattr(job, key, value)
    db.session.commit()


async def _recognise(path, shazam):
    """(title, artist) or (None, None)."""
    result = await shazam.recognize(str(path))
    track = (result or {}).get("track") or {}
    if not track:
        return None, None
    return track.get("title"), track.get("subtitle")


def _recognise_all(job, folder):
    from shazamio import Shazam

    delay = current_app.config.get("RECOGNITION_DELAY_SECONDS", 3)

    async def run():
        shazam = Shazam()
        for index, item in enumerate(job.items, 1):
            _update(job, message=f"[{index}/{job.total_files}] Recognising {item.filename}")
            try:
                title, artist = await _recognise(folder / item.filename, shazam)
            except Exception as exc:              # network error, unreadable file...
                log.warning("Shazam failed for %s: %s", item.filename, exc)
                title, artist = None, None
                item.error = str(exc)[:500]
            item.title, item.artist, item.recognized = title, artist, bool(title)
            if title:
                _update(job, event="recognized", event_text=f"{title} - {artist}",
                        message=f"Recognised {title} by {artist}", processed_files=index)
            else:
                _update(job, event="not_recognized", event_text=f"Couldn't recognise {item.filename}",
                        message=f"Couldn't recognise {item.filename}", processed_files=index)
            if delay and index < job.total_files:
                await asyncio.sleep(delay)            # stay under Shazam's rate limit

    asyncio.run(run())


def _send_to_spotify(job, sp):
    recognised = [i for i in job.items if i.recognized]
    if not recognised:
        return 0

    # Skip songs that are already in the playlist (no duplicates on re-runs).
    try:
        existing = {t["uri"] for t in get_playlist_tracks(sp, job.playlist_id)}
    except spotipy.SpotifyException:
        existing = set()

    uris = []
    for item in recognised:
        try:
            match = catalog.search_track(item.title, item.artist)
        except Exception as exc:
            log.warning("Spotify search failed for %s: %s", item.title, exc)
            match = None
        label = f"{item.title} - {item.artist}"
        if not match:
            item.added = False
            item.error = "Not found on Spotify"
            _update(job, event="not_sent", event_text=f"Not on Spotify: {label}",
                    message=f"{label} isn't on Spotify")
            continue
        item.spotify_uri = match["uri"]
        if match["uri"] in existing or match["uri"] in uris:
            item.added = True
            _update(job, event="sent", event_text=f"Already in playlist: {item.title}",
                    message=f"{label} is already in the playlist")
            continue
        uris.append(match["uri"])
        _update(job, event="sent", event_text=f"Found: {item.title}", message=f"Found {label} on Spotify")

    added = 0
    for start in range(0, len(uris), 100):             # Spotify accepts up to 100 per call
        batch = uris[start:start + 100]
        try:
            sp.playlist_add_items(job.playlist_id, batch)
            added += len(batch)
            for item in job.items:
                if item.spotify_uri in batch:
                    item.added = True
            _update(job, message=f"Added {added} of {len(uris)} songs to the playlist")
        except spotipy.SpotifyException as exc:
            log.warning("Adding batch to playlist %s failed: %s", job.playlist_id, exc)
            for item in job.items:
                if item.spotify_uri in batch:
                    item.added = False
                    item.error = f"Spotify rejected the song: {exc.msg if hasattr(exc, 'msg') else exc}"[:500]
            _update(job, event="not_sent", event_text="Spotify rejected a batch",
                    message="Spotify rejected some songs. Do you own this playlist?")
    return added


def process_job(app, job_id):
    """Thread entry point. Uses only ids, never current_user (A3)."""
    with app.app_context():
        job = db.session.get(UploadJob, job_id)
        if job is None:
            return
        folder = job_dir(job.user_id, job.public_id)
        try:
            _update(job, state="running", message="Starting...")
            _recognise_all(job, folder)

            user = db.session.get(User, job.user_id)
            sp = user_client(user)
            if sp is None:
                raise RuntimeError("Your Spotify connection has expired. Reconnect Spotify and try again.")
            added = _send_to_spotify(job, sp)

            recognised = sum(1 for i in job.items if i.recognized)
            _update(job, state="done", finished_at=utcnow(),
                    message=(f"Done! Recognised {recognised} of {job.total_files} songs and "
                             f"added {added} new song{'s' if added != 1 else ''} to {job.playlist_name or 'your playlist'}."))
        except Exception as exc:
            db.session.rollback()
            log.exception("Upload job %s failed", job_id)
            job = db.session.get(UploadJob, job_id)
            _update(job, state="failed", finished_at=utcnow(), message=f"Processing failed: {exc}")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


def recover_interrupted_jobs(app):
    """On startup: jobs that were running when the server stopped can't resume."""
    with app.app_context():
        try:
            stale = UploadJob.query.filter(UploadJob.state.in_(("queued", "running"))).all()
            for job in stale:
                job.state = "failed"
                job.message = "The server restarted while this job was running. Please upload the songs again."
                job.finished_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()


def job_status(job):
    """JSON for the progress page. Keeps the keys song_processing.html already used."""
    payload = {key: None for key in EVENT_KEYS.values()}
    if job.last_event in EVENT_KEYS:
        payload[EVENT_KEYS[job.last_event]] = job.last_event_text
    items = job.items
    payload.update({
        "job_id": job.public_id,
        "state": job.state,
        "completed": job.state in ("done", "failed"),
        "failed": job.state == "failed",
        "message": job.message,
        "total": job.total_files,
        "processed": job.processed_files,
        "counts": {
            "recognized": sum(1 for i in items if i.recognized),
            "not_recognized": sum(1 for i in items if i.recognized is False),
            "sent": sum(1 for i in items if i.added),
            "not_sent": sum(1 for i in items if i.recognized and i.added is False),
        },
        "items": [{
            "filename": i.filename, "title": i.title, "artist": i.artist,
            "recognized": i.recognized, "added": i.added, "error": i.error,
        } for i in items],
    })
    return payload

