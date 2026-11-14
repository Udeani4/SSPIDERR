"""Background jobs and `should_run_24h_task()`.

How the home feed stays fresh
-----------------------------
The home-page charts are global, so one job refreshes them for everybody:

* An APScheduler job fires at 00:00 (SCHEDULER_TIMEZONE) every day.
* A catch-up job runs every 30 minutes. It does nothing unless
  `should_run_24h_task()` says the data is stale - so if the server was asleep
  at midnight, the refresh still happens as soon as it wakes up.
* If a visitor arrives while the data is stale, `home()` serves the current
  snapshot immediately and starts a refresh in the background.

`should_run_24h_task()` returns True when the data is stale:

* the job has never succeeded, or
* the last success happened on an earlier calendar day (so data rolls over
  at midnight), or
* the last success is older than HOME_REFRESH_MAX_AGE_HOURS (default 24h).

...and returns False while the job is already running, or for 15 minutes
after a failed attempt (so a broken upstream API isn't hammered).
"""
import atexit
import logging
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app

from .extensions import db
from .models import SchedulerStatus

log = logging.getLogger(__name__)

HOME_JOB = "home_feed"
NEWS_JOB = "news_feed"
RETRY_AFTER_FAILURE = timedelta(minutes=15)
STALE_LOCK = timedelta(minutes=30)

_locks = {}
_locks_guard = threading.Lock()


def utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _job_settings(job_name):
    cfg = current_app.config
    if job_name == NEWS_JOB:
        return cfg.get("NEWS_REFRESH_HOURS", 6)
    return cfg.get("HOME_REFRESH_MAX_AGE_HOURS", 24)


def _status(job_name, create=False):
    row = SchedulerStatus.query.filter_by(job_name=job_name).first()
    if row is None and create:
        row = SchedulerStatus(job_name=job_name)
        db.session.add(row)
        db.session.commit()
    return row


def should_run_24h_task(job_name=HOME_JOB, now=None, max_age_hours=None, tz_name=None):
    """True when `job_name`'s data is stale and the job may run now. See module docstring."""
    now = _aware(now) or utcnow()
    tz = ZoneInfo(tz_name or current_app.config.get("SCHEDULER_TIMEZONE", "UTC"))
    max_age = timedelta(hours=max_age_hours or _job_settings(job_name))

    status = _status(job_name)
    if status is None:
        return True

    running_since = _aware(status.running_since)
    if running_since and now - running_since < STALE_LOCK:
        return False                      # another run is in progress

    last_attempt = _aware(status.last_attempt)
    if status.last_error and last_attempt and now - last_attempt < RETRY_AFTER_FAILURE:
        return False                      # back off after a failure

    last_run = _aware(status.last_run)
    if last_run is None:
        return True
    if now - last_run >= max_age:
        return True
    # New calendar day in the scheduler's timezone -> refresh (the "00:00" rule).
    return last_run.astimezone(tz).date() < now.astimezone(tz).date()


def job_status(job_name):
    status = _status(job_name)
    if status is None:
        return {"job": job_name, "last_run": None, "last_attempt": None, "last_error": None, "running": False}
    return {
        "job": job_name,
        "last_run": _aware(status.last_run).isoformat() if status.last_run else None,
        "last_attempt": _aware(status.last_attempt).isoformat() if status.last_attempt else None,
        "last_error": status.last_error,
        "running": bool(status.running_since),
    }


def _job_function(job_name):
    if job_name == HOME_JOB:
        from .services.home_feed import refresh_home_feed
        return refresh_home_feed
    if job_name == NEWS_JOB:
        from .services.news import refresh_news
        return refresh_news
    raise KeyError(job_name)


def _lock_for(job_name):
    with _locks_guard:
        return _locks.setdefault(job_name, threading.Lock())


def run_job(job_name, force=False):
    """Run a job if it is due (or `force`). Returns True if it ran successfully.

    Must be called inside an app context. Safe to call concurrently: only one
    run per job happens at a time.
    """
    lock = _lock_for(job_name)
    if not lock.acquire(blocking=False):
        return False
    try:
        if not force and not should_run_24h_task(job_name):
            return False

        status = _status(job_name, create=True)
        started = utcnow()
        status.running_since = started
        status.last_attempt = started
        db.session.commit()
        log.info("Job %s started", job_name)

        try:
            _job_function(job_name)()
        except Exception as exc:
            db.session.rollback()
            log.exception("Job %s failed", job_name)
            status = _status(job_name, create=True)
            status.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            status.running_since = None
            db.session.commit()
            return False

        status = _status(job_name, create=True)
        status.last_run = utcnow()
        status.last_error = None
        status.running_since = None
        db.session.commit()
        log.info("Job %s finished in %.1fs", job_name, (utcnow() - started).total_seconds())
        return True
    finally:
        lock.release()


def run_job_in_background(job_name, force=False):
    """Start `run_job` in a daemon thread (used by home() when data is stale)."""
    app = current_app._get_current_object()

    def target():
        with app.app_context():
            run_job(job_name, force=force)

    thread = threading.Thread(target=target, name=f"job-{job_name}", daemon=True)
    thread.start()
    return thread


def clear_stale_locks(app):
    """A crash mid-job leaves running_since set; clear it on startup."""
    with app.app_context():
        try:
            SchedulerStatus.query.filter(SchedulerStatus.running_since.isnot(None)).update(
                {SchedulerStatus.running_since: None})
            db.session.commit()
        except Exception:
            db.session.rollback()


# --------------------------------------------------------------------------
# APScheduler
# --------------------------------------------------------------------------
_scheduler = None
_scheduler_guard = threading.Lock()


def start_scheduler(app):
    """Start the background scheduler once per process.

    Called from the first request, so CLI commands (`flask db upgrade`) and the
    debug reloader's watcher process never start one.
    """
    global _scheduler
    if not app.config.get("SCHEDULER_ENABLED", True) or app.testing:
        return None

    with _scheduler_guard:
        if _scheduler is not None:
            return _scheduler

        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        from .services import uploads

        tz = ZoneInfo(app.config.get("SCHEDULER_TIMEZONE", "UTC"))
        scheduler = BackgroundScheduler(
            timezone=tz,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
        )

        def job(name, force=False):
            with app.app_context():
                run_job(name, force=force)

        def cleanup():
            with app.app_context():
                uploads.cleanup_old_files()
                uploads.purge_old_results()

        soon = datetime.now(tz) + timedelta(seconds=15)
        scheduler.add_job(job, CronTrigger(hour=0, minute=0, timezone=tz), args=[HOME_JOB],
                          id="home-midnight", replace_existing=True)
        scheduler.add_job(job, "interval", minutes=30, args=[HOME_JOB], id="home-catch-up",
                          next_run_time=soon, replace_existing=True)
        scheduler.add_job(job, "interval", minutes=30, args=[NEWS_JOB], id="news",
                          next_run_time=soon + timedelta(seconds=30), replace_existing=True)
        scheduler.add_job(cleanup, "interval", hours=6, id="upload-cleanup",
                          next_run_time=soon + timedelta(minutes=1), replace_existing=True)
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False))
        _scheduler = scheduler
        log.info("Scheduler started (timezone %s)", tz)
        return scheduler
