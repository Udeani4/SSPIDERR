"""should_run_24h_task() and run_job(): the home-feed refresh schedule."""
from datetime import datetime, timedelta, timezone

import pytest

from app import tasks
from app.models import SchedulerStatus

UTC = timezone.utc


def status(db, **fields):
    row = SchedulerStatus(job_name=tasks.HOME_JOB, **fields)
    db.session.add(row)
    db.session.commit()
    return row


def at(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def test_runs_when_never_run(app):
    assert tasks.should_run_24h_task(now=at(2026, 11, 14)) is True


def test_runs_when_previous_run_never_succeeded(app, db):
    status(db, last_attempt=at(2026, 11, 13))
    assert tasks.should_run_24h_task(now=at(2026, 11, 14)) is True


def test_fresh_data_same_day_does_not_run(app, db):
    status(db, last_run=at(2026, 11, 14, 1, 0))
    assert tasks.should_run_24h_task(now=at(2026, 11, 14, 23, 59)) is False


def test_runs_after_midnight_even_if_less_than_24h(app, db):
    # Refreshed at 23:50, two minutes after midnight the data is "yesterday's" -> run.
    status(db, last_run=at(2026, 11, 13, 23, 50))
    assert tasks.should_run_24h_task(now=at(2026, 11, 14, 0, 2)) is True


def test_runs_when_older_than_max_age(app, db):
    status(db, last_run=at(2026, 11, 14, 0, 0))
    assert tasks.should_run_24h_task(now=at(2026, 11, 14, 12, 0), max_age_hours=6) is True


def test_midnight_uses_configured_timezone(app, db):
    # 23:30 UTC on the 13th is already 00:30 on the 14th in Lagos (UTC+1).
    status(db, last_run=at(2026, 11, 13, 22, 0))           # 23:00 Lagos on the 13th
    now = at(2026, 11, 13, 23, 30)                          # 00:30 Lagos on the 14th
    assert tasks.should_run_24h_task(now=now, tz_name="UTC") is False
    assert tasks.should_run_24h_task(now=now, tz_name="Africa/Lagos") is True


def test_does_not_run_while_another_run_is_in_progress(app, db):
    now = at(2026, 11, 14)
    status(db, last_run=now - timedelta(days=2), running_since=now - timedelta(minutes=5))
    assert tasks.should_run_24h_task(now=now) is False


def test_ignores_a_stale_lock(app, db):
    now = at(2026, 11, 14)
    status(db, last_run=now - timedelta(days=2), running_since=now - timedelta(hours=2))
    assert tasks.should_run_24h_task(now=now) is True


def test_backs_off_after_a_failure(app, db):
    now = at(2026, 11, 14)
    status(db, last_run=now - timedelta(days=2), last_attempt=now - timedelta(minutes=5), last_error="boom")
    assert tasks.should_run_24h_task(now=now) is False
    assert tasks.should_run_24h_task(now=now + timedelta(minutes=20)) is True


def test_is_shared_by_all_visitors(app, db, client):
    """The old version kept a global counter per process and per visitor. Now there's one row per job."""
    status(db, last_run=datetime.now(UTC))
    assert tasks.should_run_24h_task() is False
    assert SchedulerStatus.query.count() == 1


# --------------------------------------------------------------------- run_job
def test_run_job_success_records_last_run(app, monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "_job_function", lambda name: (lambda: calls.append(name)))
    assert tasks.run_job(tasks.HOME_JOB) is True
    row = SchedulerStatus.query.filter_by(job_name=tasks.HOME_JOB).one()
    assert calls == [tasks.HOME_JOB]
    assert row.last_run is not None and row.running_since is None and row.last_error is None
    # Data is now fresh: a second call does nothing.
    assert tasks.run_job(tasks.HOME_JOB) is False
    assert calls == [tasks.HOME_JOB]


def test_run_job_force_runs_even_when_fresh(app, monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "_job_function", lambda name: (lambda: calls.append(name)))
    tasks.run_job(tasks.HOME_JOB)
    assert tasks.run_job(tasks.HOME_JOB, force=True) is True
    assert len(calls) == 2


def test_run_job_failure_keeps_old_success_and_records_error(app, db, monkeypatch):
    good = datetime(2026, 11, 1, tzinfo=UTC)
    status(db, last_run=good)

    def broken():
        raise RuntimeError("Billboard is down")
    monkeypatch.setattr(tasks, "_job_function", lambda name: broken)
    assert tasks.run_job(tasks.HOME_JOB) is False
    row = SchedulerStatus.query.filter_by(job_name=tasks.HOME_JOB).one()
    assert "Billboard is down" in row.last_error
    assert row.running_since is None
    assert row.last_run.replace(tzinfo=UTC) == good          # old data stays "last good"


def test_run_job_is_not_reentrant(app, monkeypatch):
    lock = tasks._lock_for(tasks.HOME_JOB)
    lock.acquire()
    try:
        monkeypatch.setattr(tasks, "_job_function", lambda name: pytest.fail("must not run"))
        assert tasks.run_job(tasks.HOME_JOB, force=True) is False
    finally:
        lock.release()


def test_clear_stale_locks(app, db):
    status(db, running_since=datetime.now(UTC))
    tasks.clear_stale_locks(app)
    assert SchedulerStatus.query.one().running_since is None
