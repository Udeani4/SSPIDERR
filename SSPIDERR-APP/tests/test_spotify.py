"""Spotify helpers: playlist listing without N+1 calls, robust track parsing, token refresh."""
import time

import pytest
from spotipy.oauth2 import SpotifyOauthError

from app.services import spotify
from tests.conftest import FakeSpotify, make_user, playlist_item, track_entry


def test_get_user_playlists_uses_only_the_listing(app):
    sp = FakeSpotify(playlists=[playlist_item("p1"), playlist_item("p2", owner="other", images=False)])
    result = spotify.get_user_playlists(sp, 1, me_id="me")
    assert [name for name, _ in sp.calls] == ["current_user_playlists"]          # P1: no per-playlist calls
    assert result[0]["image"] == "http://img/p1/1"
    assert result[1]["image"] == spotify.PLAYLIST_PLACEHOLDER                     # B3: no crash without cover
    assert result[0]["editable"] is True and result[1]["editable"] is False
    assert result[0]["num_tracks"] == 3


def test_get_user_playlists_handles_renamed_items_field(app):
    item = playlist_item("p1")
    item["items"] = item.pop("tracks")
    sp = FakeSpotify(playlists=[item])
    assert spotify.get_user_playlists(sp, me_id="me")[0]["tracks"] == 3


@pytest.mark.parametrize("entry", [
    {"track": None},                                                  # removed track
    {"track": {"id": None, "type": "track"}},                         # local file
    {"track": {"id": "e1", "type": "episode"}},                       # podcast episode
])
def test_parse_playlist_track_skips_unusable_entries(entry):
    assert spotify.parse_playlist_track(entry) is None


def test_parse_playlist_track_without_images_or_popularity():
    entry = track_entry("t1", images=False)
    del entry["track"]["popularity"]
    parsed = spotify.parse_playlist_track(entry)
    assert parsed["image"] == spotify.TRACK_PLACEHOLDER                # B4
    assert parsed["popularity"] == 0


def test_parse_playlist_track_reads_new_item_key():
    assert spotify.parse_playlist_track(track_entry("t9", key="item"))["id"] == "t9"


def test_playlist_stats():
    tracks = [spotify.parse_playlist_track(track_entry(f"t{i}", popularity=p, duration=30 * 60_000))
              for i, p in enumerate([40, 60, 80])]
    assert spotify.playlist_stats(tracks) == {"avg_popularity": 60, "total_duration_hours": 1,
                                              "total_duration_minutes": 30}
    assert spotify.playlist_stats([])["avg_popularity"] == 0


def test_format_artists():
    assert spotify.format_artists({"artists": [{"name": "A"}]}) == "A"
    assert spotify.format_artists({"artists": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}) == "A ft. B, C"
    assert spotify.format_artists({"artists": []}) == "Unknown artist"


# --------------------------------------------------------------------- tokens (B12)
def test_valid_token_is_reused_without_any_network_call(app, monkeypatch):
    user = make_user()
    monkeypatch.setattr(spotify, "oauth_manager", lambda *a, **k: pytest.fail("should not refresh"))
    assert spotify.get_valid_access_token(user) == user.spotify_acc_tok


def test_expiring_token_is_refreshed_and_saved(app, monkeypatch):
    user = make_user()
    user.spotify_token_expires_at = int(time.time()) + 10          # about to expire

    class Manager:
        def refresh_access_token(self, refresh_token):
            info = {"access_token": "fresh", "refresh_token": None, "expires_at": int(time.time()) + 3600}
            spotify.DBTokenCache(user).save_token_to_cache(info)
            return info

    monkeypatch.setattr(spotify, "oauth_manager", lambda u=None: Manager())
    assert spotify.get_valid_access_token(user) == "fresh"
    assert user.spotify_acc_tok == "fresh"
    assert user.spotify_ref_tok == "refresh-user@example.com"      # kept when Spotify doesn't rotate it
    assert user.spotify_token_expires_at > time.time() + 3000


def test_revoked_refresh_token_clears_the_connection(app, monkeypatch):
    user = make_user()
    user.spotify_token_expires_at = None

    class Manager:
        def refresh_access_token(self, refresh_token):
            raise SpotifyOauthError("invalid_grant")

    monkeypatch.setattr(spotify, "oauth_manager", lambda u=None: Manager())
    assert spotify.get_valid_access_token(user) is None
    assert user.spotify_ref_tok is None and not user.has_spotify


def test_anonymous_user_gets_no_token(app):
    from flask_login import AnonymousUserMixin
    assert spotify.get_valid_access_token(AnonymousUserMixin()) is None
    assert spotify.get_valid_access_token(None) is None


def test_sync_user_library_skips_unchanged_playlists(app, db):
    from app.models import Playlist, Songs
    sp = FakeSpotify(tracks={"p1": [track_entry("t1"), track_entry("t2")]})
    playlists = [dict(id="p1", name="Mix", description="", snapshot_id="s1")]
    spotify.sync_user_library(app, "me", sp, playlists)
    assert Songs.query.filter_by(spotify_user_id="me").count() == 2
    assert Playlist.query.one().snapshot_id == "s1"

    sp.calls.clear()
    spotify.sync_user_library(app, "me", sp, playlists)                 # same snapshot -> no downloads
    assert not any(name == "playlist_items" for name, _ in sp.calls)

    spotify.sync_user_library(app, "me", sp, [])                         # playlist deleted on Spotify
    assert Playlist.query.count() == 0 and Songs.query.count() == 0
