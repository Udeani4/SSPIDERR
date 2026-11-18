"""Spotify Development Mode: accounts that aren't on the app's user list get a clear explanation."""
import spotipy
from flask import g

from app.services import spotify as spotify_service
from tests.conftest import make_user

NOT_REGISTERED = spotipy.SpotifyException(
    403, -1, "https://api.spotify.com/v1/me:\n Check settings on developer.spotify.com/dashboard, "
             "the user may not be registered.")


def test_is_not_registered():
    assert spotify_service.is_not_registered(NOT_REGISTERED)
    assert not spotify_service.is_not_registered(spotipy.SpotifyException(403, -1, "Forbidden: not your playlist"))
    assert not spotify_service.is_not_registered(spotipy.SpotifyException(404, -1, "not registered"))
    assert not spotify_service.is_not_registered(ValueError("x"))


def test_callback_explains_invite_only_and_clears_tokens(client, db, monkeypatch):
    user = make_user(spotify=False)
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["spotify_oauth_state"] = "abc"

    class Manager:
        def get_access_token(self, code, as_dict=False, check_cache=False):
            user.spotify_acc_tok, user.spotify_ref_tok = "tok", "ref"     # spotipy saves before /me
            db.session.commit()
            return "tok"

    class Refusing:
        def __init__(self, **kwargs):
            pass

        def me(self):
            raise NOT_REGISTERED

    monkeypatch.setattr(spotify_service, "oauth_manager", lambda u=None: Manager())
    monkeypatch.setattr(spotipy, "Spotify", Refusing)
    res = client.get("/callback?state=abc&code=xyz")
    assert res.status_code == 302 and "invite_only=1" in res.headers["Location"]
    assert user.spotify_ref_tok is None and not user.has_spotify                # not stuck half-connected

    g.pop("_login_user", None)
    page = client.get(res.headers["Location"]).get_data(as_text=True)
    assert "invite-only" in page and "Contact us" in page


def test_connect_page_without_flag_has_no_warning(client, db):
    user = make_user(spotify=False)
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
    assert "invite-only" not in client.get("/connect-spotify").get_data(as_text=True)


class RefusedSpotify:
    def me(self):
        raise NOT_REGISTERED

    def current_user_playlists(self, limit=50):
        raise NOT_REGISTERED

    def playlist_add_items(self, *a):
        raise NOT_REGISTERED

    def playlist(self, *a, **k):
        raise NOT_REGISTERED


def test_playlist_picker_and_add_explain_invite_only(logged_in, user, monkeypatch):
    import app.blueprints.library as library
    monkeypatch.setattr(library.spotify_service, "user_client", lambda *a, **k: RefusedSpotify())
    res = logged_in.get("/api/my-playlists")
    assert res.status_code == 403 and res.get_json()["invite_only"] is True
    assert "invite-only" in res.get_json()["error"]

    user.spotify_ref_tok = "ref"                                                 # reconnect for the next call
    res = logged_in.post("/add_to_playlist", json={"playlist_id": "p1", "track_id": "t1"})
    assert res.status_code == 403 and res.get_json()["invite_only"] is True
    assert not user.has_spotify


def test_any_other_page_shows_invite_only_error(logged_in, user, monkeypatch):
    import app.utils as utils
    monkeypatch.setattr(utils, "user_client", lambda *a, **k: RefusedSpotify())
    res = logged_in.get("/playlist-page/p1")
    assert res.status_code == 403 and b"invite-only" in res.data
    assert not user.has_spotify


def test_upload_job_stops_with_invite_only_message(app, db, monkeypatch):
    import io

    import shazamio
    from werkzeug.datastructures import FileStorage

    from app.models import UploadJob
    from app.services import catalog, uploads

    class Shazam:
        async def recognize(self, path):
            return {"track": {"title": "Song", "subtitle": "Artist"}}

    class RefusingSp:
        def playlist_items(self, *a, **k):
            raise NOT_REGISTERED

    monkeypatch.setattr(shazamio, "Shazam", Shazam)
    monkeypatch.setattr(uploads, "user_client", lambda *a, **k: RefusingSp())
    monkeypatch.setattr(catalog, "search_track", lambda *a, **k: {"uri": "spotify:track:x", "id": "x"})
    user = make_user()
    uploads.save_upload(user.id, FileStorage(stream=io.BytesIO(b"x"), filename="a.mp3"))
    job, _ = uploads.create_job(user, "p1")
    uploads.process_job(app, job.id)
    db.session.expire_all()
    job = db.session.get(UploadJob, job.id)
    assert job.state == "failed" and "invite-only" in job.message and "Do you own" not in job.message
