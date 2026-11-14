"""Shared fixtures. No test touches the network: every external call is faked."""
import time
from types import SimpleNamespace

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User


class FakeSpotify:
    """Minimal stand-in for spotipy.Spotify. Records every call in `.calls`."""

    def __init__(self, playlists=None, tracks=None, me_id="me"):
        self.calls = []
        self._playlists = playlists if playlists is not None else []
        self._tracks = tracks if tracks is not None else {}
        self.me_id = me_id
        self.added = []
        self.created = []

    def _log(self, name, *args):
        self.calls.append((name, args))

    def me(self):
        self._log("me")
        return {"id": self.me_id}

    def current_user_playlists(self, limit=50):
        self._log("current_user_playlists", limit)
        return {"items": self._playlists, "next": None}

    def next(self, results):
        return None

    def playlist(self, playlist_id, fields=None, **_):
        self._log("playlist", playlist_id)
        return {"id": playlist_id, "name": f"Playlist {playlist_id}", "description": "", "images": [],
                "owner": {"id": self.me_id, "display_name": "Me"}, "external_urls": {"spotify": "https://x"}}

    def playlist_items(self, playlist_id, limit=100, additional_types=None, market=None, **_):
        self._log("playlist_items", playlist_id)
        return {"items": self._tracks.get(playlist_id, []), "next": None}

    def playlist_add_items(self, playlist_id, items):
        self._log("playlist_add_items", playlist_id, tuple(items))
        self.added.append((playlist_id, list(items)))

    def user_playlist_create(self, user, name, description="", **_):
        self._log("user_playlist_create", user, name)
        self.created.append(name)
        return {"id": "new-playlist"}


def track_entry(track_id, name="Song", artist="Artist", popularity=50, duration=200_000, key="track", images=True):
    return {key: {
        "id": track_id, "name": name, "type": "track", "uri": f"spotify:track:{track_id}",
        "album": {"name": "Album", "images": [{"url": f"http://img/{track_id}"}] if images else []},
        "artists": [{"name": artist}], "duration_ms": duration, "popularity": popularity,
        "preview_url": None, "external_urls": {"spotify": f"https://open.spotify.com/track/{track_id}"},
    }}


def playlist_item(pid, name="Mix", owner="me", total=3, images=True, snapshot="s1"):
    return {"id": pid, "name": name, "owner": {"id": owner, "display_name": owner}, "collaborative": False,
            "tracks": {"total": total}, "images": [{"url": f"http://img/{pid}/0"}, {"url": f"http://img/{pid}/1"}] if images else [],
            "description": "", "public": True, "snapshot_id": snapshot}


@pytest.fixture
def app(tmp_path):
    app = create_app("testing", instance_path=tmp_path / "instance")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(email="user@example.com", password="password123", spotify=True):
    from werkzeug.security import generate_password_hash
    user = User(email=email, password=generate_password_hash(password))
    if spotify:
        user.spotify_acc_tok = f"access-{email}"
        user.spotify_ref_tok = f"refresh-{email}"
        user.spotify_user_id = "me" if email == "user@example.com" else f"sp-{email}"
        user.spotify_token_expires_at = int(time.time()) + 3600
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def user(app):
    return make_user()


@pytest.fixture
def logged_in(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


@pytest.fixture
def fake_sp(monkeypatch):
    """Patch every place that creates a user Spotify client."""
    sp = FakeSpotify(
        playlists=[playlist_item("p1", "Road trip"), playlist_item("p2", "Not mine", owner="someone")],
        tracks={"p1": [track_entry("t1", "One"), track_entry("t2", "Two")]},
    )
    import app.blueprints.library as library
    import app.services.spotify as spotify_service
    import app.services.uploads as uploads
    import app.utils as utils
    for module in (spotify_service, utils, uploads):
        monkeypatch.setattr(module, "user_client", lambda *a, **k: sp)
    monkeypatch.setattr(library.spotify_service, "user_client", lambda *a, **k: sp)
    monkeypatch.setattr(spotify_service, "start_library_sync", lambda *a, **k: None)
    return sp


@pytest.fixture
def offline(monkeypatch):
    """Make every catalogue / scraper / HTTP call return canned data."""
    import app.services.catalog as catalog
    import app.services.charts as charts
    import app.services.http as http
    import app.services.scrapers as scrapers

    monkeypatch.setattr(http, "get_json", lambda *a, **k: k.get("default"))

    def no_network(*a, **k):
        raise RuntimeError("network disabled in tests")
    monkeypatch.setattr(http, "get_text", no_network)

    track = {"id": "a" * 22, "uri": "spotify:track:" + "a" * 22, "name": "Song", "artist": "Artist",
             "image": "http://img/t", "album_id": "b" * 22, "preview_url": "http://preview"}
    monkeypatch.setattr(catalog, "search_track", lambda *a, **k: dict(track))
    monkeypatch.setattr(catalog, "search_album", lambda *a, **k: {"id": "b" * 22, "name": "Album", "artist": "Artist",
                                                                  "image": "http://img/a", "release_date": "2024-01-01"})
    monkeypatch.setattr(catalog, "artist_image", lambda *a, **k: "http://img/artist")
    monkeypatch.setattr(catalog, "itunes_preview", lambda *a, **k: {"preview_url": "http://itunes/p", "itunes_url": "http://itunes"})
    monkeypatch.setattr(catalog, "artist_description", lambda *a, **k: {"source": "Last.fm", "description": "<b>Bio</b>"})
    monkeypatch.setattr(catalog, "similar_artists", lambda name, limit=8: [f"{name} Friend {i}" for i in range(3)])
    monkeypatch.setattr(catalog, "lastfm", lambda method, **p: {})
    monkeypatch.setattr(scrapers, "billboard_chart", lambda endpoint="hot-100", chart_date=None, limit=10: (
        [{"song": f"Hit {i}", "artist": "Star, Guest", "main_artist": "Star"} for i in range(limit)],
        scrapers.chart_type(endpoint)))
    monkeypatch.setattr(scrapers, "audiomack_chart", lambda key, limit=10: [
        {"artist": "Wizkid", "title": f"{key} {i}", "main_artist": "Wizkid"} for i in range(3)])
    monkeypatch.setattr(charts, "grammy_winners", lambda year: [
        {"category": "Record Of The Year", "title": "Song", "artist": "Artist", "kind": "song",
         "spotify_id": "a" * 22, "image": None, "preview_url": None}])
    return SimpleNamespace(track=track)


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    """Safety net: any test that forgets to fake a request fails fast instead of waiting on the network."""
    import app.services.http as http

    def blocked(*args, **kwargs):
        raise RuntimeError("Real HTTP request attempted in a test")
    monkeypatch.setattr(http.HTTP, "get", blocked)
    monkeypatch.setattr(http.HTTP_FAST, "get", blocked)
