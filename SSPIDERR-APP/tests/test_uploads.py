"""Upload -> recognise -> add-to-playlist pipeline (A5 / B21), with Shazam and Spotify faked."""
import io

import pytest
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import UploadJob
from app.services import uploads
from tests.conftest import make_user


def storage(name, data=b"ID3fake-mp3"):
    return FileStorage(stream=io.BytesIO(data), filename=name)


class FakeShazam:
    """Recognises files whose name starts with 'hit', fails the rest."""

    async def recognize(self, path):
        name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
        if name.startswith("hit"):
            return {"track": {"title": f"Title {name}", "subtitle": "Artist"}}
        return {"matches": []}


@pytest.fixture(autouse=True)
def fake_shazam(monkeypatch):
    import shazamio
    monkeypatch.setattr(shazamio, "Shazam", FakeShazam)


def test_save_upload_validates_files(app):
    assert uploads.save_upload(1, storage("song.mp3"))[0] is True
    ok, message, _ = uploads.save_upload(1, storage("music.zip"))
    assert not ok and "ZIP" in message
    ok, message, _ = uploads.save_upload(1, storage("notes.txt"))
    assert not ok and "supported" in message
    ok, _, _ = uploads.save_upload(1, storage("../../.mp3"))          # nothing left after secure_filename
    assert not ok


def test_uploads_never_overwrite_and_are_per_user(app):
    assert uploads.save_upload(1, storage("song.mp3"))[2] == "song.mp3"
    assert uploads.save_upload(1, storage("song.mp3"))[2] == "song-1.mp3"
    uploads.save_upload(2, storage("other.mp3"))
    assert uploads.list_pending(1) == ["song-1.mp3", "song.mp3"]
    assert uploads.list_pending(2) == ["other.mp3"]
    assert uploads.delete_pending(1, "song.mp3") is True
    assert uploads.list_pending(1) == ["song-1.mp3"]


def test_create_job_moves_files_and_is_idempotent(app):
    user = make_user()
    uploads.save_upload(user.id, storage("hit-a.mp3"))
    job, created = uploads.create_job(user, "p1", "Road trip")
    assert created and job.total_files == 1 and uploads.list_pending(user.id) == []
    again, created_again = uploads.create_job(user, "p1")              # reload while running
    assert again.id == job.id and created_again is False


def test_create_job_without_files(app):
    with pytest.raises(uploads.JobError):
        uploads.create_job(make_user(), "p1")


def test_process_job_end_to_end(app, fake_sp, monkeypatch):
    from app.services import catalog
    monkeypatch.setattr(catalog, "search_track", lambda title, artist=None: (
        {"uri": f"spotify:track:{title[-6:]}", "id": "x"} if "hit-b" not in title else None))
    fake_sp._tracks["p1"] = []
    user = make_user()
    for name in ("hit-a.mp3", "hit-b.mp3", "noise.mp3"):
        uploads.save_upload(user.id, storage(name))
    job, _ = uploads.create_job(user, "p1", "Road trip")

    uploads.process_job(app, job.id)

    db.session.expire_all()
    job = db.session.get(UploadJob, job.id)
    status = uploads.job_status(job)
    assert job.state == "done" and status["completed"] is True
    assert status["counts"] == {"recognized": 2, "not_recognized": 1, "sent": 1, "already": 0, "not_sent": 1}
    assert len(fake_sp.added) == 1 and len(fake_sp.added[0][1]) == 1   # only the song found on Spotify
    assert not uploads.job_dir(user.id, job.public_id).exists()         # cleaned up
    assert "Recognised 2 of 3" in job.message


def test_process_job_skips_songs_already_in_playlist(app, fake_sp, monkeypatch):
    from app.services import catalog
    from tests.conftest import track_entry
    monkeypatch.setattr(catalog, "search_track", lambda *a, **k: {"uri": "spotify:track:dup", "id": "dup"})
    fake_sp._tracks["p1"] = [track_entry("dup")]
    user = make_user()
    uploads.save_upload(user.id, storage("hit-a.mp3"))
    job, _ = uploads.create_job(user, "p1")
    uploads.process_job(app, job.id)
    assert fake_sp.added == []
    db.session.expire_all()
    job = db.session.get(UploadJob, job.id)
    item = job.items[0]
    assert item.already_in_playlist is True and not item.added            # labelled, not counted as "added"
    status = uploads.job_status(job)
    assert status["counts"]["already"] == 1 and status["counts"]["sent"] == 0
    assert status["items"][0]["already_in_playlist"] is True
    assert "already in the playlist" in job.message


def test_process_job_fails_cleanly_without_spotify(app, monkeypatch):
    monkeypatch.setattr(uploads, "user_client", lambda *a, **k: None)
    user = make_user()
    uploads.save_upload(user.id, storage("hit-a.mp3"))
    job, _ = uploads.create_job(user, "p1")
    uploads.process_job(app, job.id)
    db.session.expire_all()
    job = db.session.get(UploadJob, job.id)
    assert job.state == "failed" and "Reconnect Spotify" in job.message


def test_job_status_is_private(app, client):
    owner, other = make_user(), make_user("other@example.com")
    uploads.save_upload(owner.id, storage("hit-a.mp3"))
    job, _ = uploads.create_job(owner, "p1")
    with client.session_transaction() as sess:
        sess["_user_id"] = str(other.id)
    assert client.get(f"/jobs/{job.public_id}/status").status_code == 404


def test_recover_interrupted_jobs(app):
    user = make_user()
    uploads.save_upload(user.id, storage("hit-a.mp3"))
    job, _ = uploads.create_job(user, "p1")
    uploads.recover_interrupted_jobs(app)
    db.session.expire_all()
    assert db.session.get(UploadJob, job.id).state == "failed"


def test_upload_route_requires_login(client):
    data = {"file": (io.BytesIO(b"x"), "a.mp3")}
    assert client.post("/upload-song", data=data, content_type="multipart/form-data").status_code == 302


def test_upload_route_saves_file(logged_in, user, app):
    data = {"file": (io.BytesIO(b"x"), "my song.mp3")}
    res = logged_in.post("/upload-song", data=data, content_type="multipart/form-data")
    assert res.status_code == 200 and res.get_json() == {"success": True, "filename": "my_song.mp3"}
    assert uploads.list_pending(user.id) == ["my_song.mp3"]


def test_purge_old_results(app, db):
    from datetime import datetime, timedelta, timezone

    from app.models import UploadJobItem
    user = make_user()
    now = datetime.now(timezone.utc)

    def job(state, age_days):
        j = UploadJob(public_id=f"{state}-{age_days}", user_id=user.id, playlist_id="p1", state=state,
                      created_at=now - timedelta(days=age_days),
                      finished_at=(now - timedelta(days=age_days)) if state in ("done", "failed") else None)
        j.items.append(UploadJobItem(filename="a.mp3"))
        db.session.add(j)
        return j
    job("done", 45), job("failed", 31), job("done", 5), job("running", 60)
    db.session.commit()

    assert uploads.purge_old_results(30) == 2
    assert sorted(j.public_id for j in UploadJob.query) == ["done-5", "running-60"]   # recent + still running kept
    assert UploadJobItem.query.count() == 2
    assert uploads.purge_old_results(0) == 0                                          # 0 = keep forever


def test_expired_results_link_never_starts_a_new_job(logged_in, user, fake_sp):
    uploads.save_upload(user.id, storage("hit-a.mp3"))                   # pending files exist...
    html = logged_in.get("/song-processing/p1?job=deleted-job-id").get_data(as_text=True)
    assert 'data-job-missing="1"' in html                                  # ...but the page won't auto-start
    assert logged_in.get("/jobs/deleted-job-id/status").status_code == 404
    assert UploadJob.query.count() == 0
