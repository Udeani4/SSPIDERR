"""Every page renders for anonymous and logged-in users (B9/B10), plus auth & security behaviour."""
from datetime import datetime, timezone

import pytest
from flask import g

from app import tasks
from app.models import BlogPost, Comment, HomeData, SchedulerStatus, User
from tests.conftest import make_user

SPOTIFY_ID = "a" * 22


class FakeCatalogClient:
    """App-level Spotify client for song/album/artist pages."""

    def track(self, track_id):
        return {"id": track_id, "name": "Song", "popularity": 70, "duration_ms": 1000, "preview_url": None,
                "external_urls": {"spotify": "https://s"}, "artists": [{"id": "ar", "name": "Artist"}],
                "album": {"id": "b" * 22, "name": "Album", "release_date": "2024-05-01", "images": []}}

    def album(self, album_id):
        return {"id": album_id, "name": "Album", "release_date": "2024-05-01", "popularity": 50, "images": [],
                "external_urls": {"spotify": "https://s"}, "artists": [{"name": "Artist"}],
                "tracks": {"items": [{"id": "c" * 22, "name": "Track", "artists": [{"name": "Artist"}]}]}}

    def artist_top_tracks(self, artist_id, country="US"):
        return {"tracks": [{"id": "t" * 22, "name": "Top", "artists": [{"name": "Artist"}], "album": {"images": []}}]}

    def artist_albums(self, artist_id, album_type=None, limit=20):
        return {"items": [{"id": "b" * 22, "name": "Album", "album_type": "album", "release_date": "2024-05-01",
                           "release_date_precision": "day", "images": [], "total_tracks": 10}]}

    def album_tracks(self, album_id, limit=50):
        return {"items": [{"id": "c" * 22, "name": "Track", "artists": [{"name": "Artist"}], "duration_ms": 1}]}

    def search(self, q, type, limit=1):
        return {f"{type}s": {"items": []}}

    def new_releases(self, country="US", limit=30):
        return {"albums": {"items": []}}


@pytest.fixture
def catalog_client(monkeypatch):
    import app.blueprints.music as music
    import app.services.catalog as catalog
    fake = FakeCatalogClient()
    monkeypatch.setattr(music, "app_client", lambda: fake)
    monkeypatch.setattr(catalog, "app_client", lambda: fake)
    monkeypatch.setattr(catalog, "search_artist", lambda name: {
        "id": "ar", "name": name, "images": [], "followers": {"total": 5}, "genres": ["pop"], "popularity": 60,
        "external_urls": {"spotify": "https://s"}})
    monkeypatch.setattr(catalog, "artist_profile", lambda name: {"artist_name": name, "followers": 1, "popularity": 2})
    monkeypatch.setattr(catalog, "album_tracks_sorted", lambda album_id: [{"id": "c" * 22, "name": "Track"}])
    monkeypatch.setattr(catalog, "new_releases", lambda limit=10: [])
    return fake


@pytest.fixture
def home_data(db):
    db.session.add(SchedulerStatus(job_name=tasks.HOME_JOB, last_run=datetime.now(timezone.utc)))
    db.session.add(HomeData(album_name="GNX", album_id="1", song_name="Luther", song_id="2", artist_name="Kendrick",
                            top_albums=[], this_weeks_hits=[], best_2025_hits=[], artist_section_dict={}))
    db.session.commit()


@pytest.fixture
def post(db):
    p = BlogPost(title="News", subtitle="<b>Summary</b>", body="Body", created_id=7, day=1, month="Nov", year=2026,
                 news_link="https://news", source="Billboard", date=datetime(2026, 11, 1))
    db.session.add(p)
    db.session.commit()
    return p


PUBLIC_PAGES = [
    "/", "/about-us", "/about-us/overview", "/about-us/discover", "/about-us/new_releases", "/about-us/newsroom",
    "/about-us/local_spotify", "/about-us/playlist_hub", "/contact", "/news-blog", "/blog-post/7",
    "/login-page", "/register-page", "/see-whats-new", "/see-whats-new-results?keyword=hot-100",
    "/see-whats-new-results?keyword=billboard-200&release-date=2025-10-18", "/see-whats-new-results?keyword=artist-100",
    "/US-top-40-songs", "/top-hits-time-travel", "/top-hits-time-travel?date=1999-12-25", "/suggested-songs",
    "/award-winning-songs", "/afro-beats", f"/song-page/{SPOTIFY_ID}", f"/album-page/{'b' * 22}", "/artist-page/Drake",
]


@pytest.mark.parametrize("url", PUBLIC_PAGES)
def test_public_pages_render_for_anonymous_visitors(client, home_data, post, offline, catalog_client, url):
    res = client.get(url)
    assert res.status_code == 200, res.data[:500]


@pytest.mark.parametrize("url", PUBLIC_PAGES + ["/playlist", "/playlist-page/p1", "/create-playlist", "/loader-page",
                                                "/connect-spotify", "/song-processing/p1"])
def test_pages_render_for_logged_in_users(logged_in, fake_sp, home_data, post, offline, catalog_client, url):
    res = logged_in.get(url)
    assert res.status_code in (200, 302), res.data[:500]


@pytest.mark.parametrize("url", ["/playlist", "/playlist-page/p1", "/create-playlist", "/loader-page",
                                 "/display-uploads", "/song-processing/p1", "/status/jobs"])
def test_private_pages_redirect_anonymous_to_login(client, url):
    res = client.get(url)
    assert res.status_code == 302 and "/login-page" in res.headers["Location"]


def test_private_pages_ask_to_connect_spotify(client, db):
    user = make_user(spotify=False)
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
    res = client.get("/playlist")
    assert res.status_code == 302 and "/connect-spotify" in res.headers["Location"]


def test_unknown_items_show_friendly_404(client, offline, catalog_client):
    assert client.get("/song-page/not-a-real-id!").status_code == 404
    assert client.get("/blog-post/9999").status_code == 404
    res = client.get("/no-such-page")
    assert res.status_code == 404 and b"Page not found" in res.data


def test_home_builds_feed_on_first_ever_visit(client, monkeypatch, db):
    built = []

    def fake_run_job(name, force=False):
        built.append((name, force))
        db.session.add(HomeData(album_name="Fresh", top_albums=[]))
        db.session.commit()
    monkeypatch.setattr(tasks, "run_job", fake_run_job)
    res = client.get("/")
    assert res.status_code == 200 and b"Fresh" in res.data and built == [(tasks.HOME_JOB, True)]


def test_home_serves_stale_data_and_refreshes_in_background(client, monkeypatch, db):
    db.session.add(HomeData(album_name="Old charts", top_albums=[]))
    db.session.add(SchedulerStatus(job_name=tasks.HOME_JOB, last_run=datetime(2020, 1, 1, tzinfo=timezone.utc)))
    db.session.commit()
    started = []
    monkeypatch.setattr(tasks, "run_job_in_background", lambda name, force=False: started.append(name))
    res = client.get("/")
    assert res.status_code == 200 and b"Old charts" in res.data and started == [tasks.HOME_JOB]


def test_home_survives_when_every_source_fails(client, monkeypatch):
    monkeypatch.setattr(tasks, "run_job", lambda *a, **k: False)
    res = client.get("/")
    assert res.status_code == 200 and b"being refreshed" in res.data


# --------------------------------------------------------------------- auth
def test_register_login_logout(client, db):
    res = client.post("/register-page", data={"email": "New@Example.com", "password": "longpassword",
                                              "verify_password": "longpassword"})
    assert res.status_code == 302 and "/connect-spotify" in res.headers["Location"]
    user = User.query.filter_by(email="new@example.com").one()
    assert user.password.startswith("scrypt:")                                 # S5
    client.get("/logout")
    res = client.post("/login-page", data={"email": "new@example.com", "password": "longpassword", "next": "/about-us"})
    assert res.status_code == 302 and res.headers["Location"].endswith("/about-us")


@pytest.mark.parametrize("form, message", [
    ({"email": "bad", "password": "longpassword", "verify_password": "longpassword"}, b"valid email"),
    ({"email": "a@b.co", "password": "short", "verify_password": "short"}, b"at least 8"),
    ({"email": "a@b.co", "password": "longpassword", "verify_password": "different1"}, b"match"),
])
def test_register_validation(client, form, message):
    res = client.post("/register-page", data=form)
    assert res.status_code == 400 and message in res.data


def test_login_rejects_wrong_password_without_revealing_accounts(client, user):
    wrong_pw = client.post("/login-page", data={"email": user.email, "password": "nope"})
    no_user = client.post("/login-page", data={"email": "ghost@example.com", "password": "nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert b"Incorrect email or password" in wrong_pw.data and b"Incorrect email or password" in no_user.data


def test_login_ignores_external_next(client, user):
    res = client.post("/login-page", data={"email": user.email, "password": "password123",
                                           "next": "https://evil.example/"})
    assert res.headers["Location"] == "/"                                       # S3


def test_deleted_user_cookie_logs_out_instead_of_404(client, user, db):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
    db.session.delete(user)
    db.session.commit()
    assert client.get("/about-us").status_code == 200                           # B11


# --------------------------------------------------------------------- playlists
def test_api_my_playlists(client, logged_in, fake_sp):
    data = logged_in.get("/api/my-playlists").get_json()
    assert [p["id"] for p in data["playlists"]] == ["p1"]                       # only editable ones


def test_api_my_playlists_requires_login(client):
    assert client.get("/api/my-playlists").status_code == 401


def test_add_to_playlist(logged_in, fake_sp):
    res = logged_in.post("/add_to_playlist", json={"playlist_id": "p1", "track_id": "t9"})
    assert res.get_json()["success"] is True
    assert fake_sp.added == [("p1", ["spotify:track:t9"])]
    assert logged_in.post("/add_to_playlist", json={}).status_code == 400


def test_create_playlist_rejects_duplicates_and_creates(logged_in, fake_sp):
    dup = logged_in.post("/create-playlist", data={"name": "road trip"})
    assert dup.status_code == 400 and fake_sp.created == []
    res = logged_in.post("/create-playlist", data={"name": "Brand new", "next": "/loader-page"})
    assert res.status_code == 302 and res.headers["Location"] == "/loader-page" and fake_sp.created == ["Brand new"]


def test_playlist_page_stats_come_from_tracks(logged_in, fake_sp):
    res = logged_in.get("/playlist-page/p1")
    assert res.status_code == 200 and b"One" in res.data and b"Awards" not in res.data


# --------------------------------------------------------------------- news & reviews
def test_comment_html_is_sanitised(logged_in, post, db):
    res = logged_in.post("/blog-post/7", data={"comment_text": '<p>Nice</p><img src=x onerror="alert(1)">'})
    assert res.status_code == 302
    comment = Comment.query.one()
    assert "<img" not in comment.text and "&lt;img" in comment.text and "Nice" in comment.text   # S1: escaped
    page = logged_in.get("/blog-post/7").get_data(as_text=True)
    assert "<img src=x" not in page


def test_only_author_can_delete_comment(client, post, db):
    author, other = make_user(), make_user("other@example.com")
    comment = Comment(text="hi", author_id=author.id, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(other.id)
    assert client.post(f"/delete-comment/{comment.id}").status_code == 403
    g.pop("_login_user", None)          # the test keeps one app context open; forget the cached user
    with client.session_transaction() as sess:
        sess["_user_id"] = str(author.id)
    assert client.post(f"/delete-comment/{comment.id}").status_code == 302
    assert Comment.query.count() == 0


def test_review_requires_login_and_text(client, logged_in, db):
    from app.models import ReviewComment
    logged_in.post("/about-us", data={"review": "   "})
    assert ReviewComment.query.count() == 0                                    # B17
    logged_in.post("/about-us", data={"review": "Great app"})
    assert ReviewComment.query.one().text == "Great app"


def test_anonymous_review_redirects_to_login(app):
    c = app.test_client()
    res = c.post("/about-us", data={"review": "hi"})
    assert res.status_code == 302 and "/login-page" in res.headers["Location"]


def test_contact_validation_and_failure(client, monkeypatch):
    import app.blueprints.main as main
    assert client.post("/contact", data={"name": "", "email": "x", "message": ""}).status_code == 400

    def broken(*a):
        raise OSError("smtp down")
    monkeypatch.setattr(main, "send_email", broken)
    res = client.post("/contact", data={"name": "A", "email": "a@b.co", "message": "Hello"})
    assert res.status_code == 503                                               # B23: no 500

    sent = []
    monkeypatch.setattr(main, "send_email", lambda *a: sent.append(a))
    assert client.post("/contact", data={"name": "A", "email": "a@b.co", "message": "Hello"}).status_code == 302
    assert sent


# --------------------------------------------------------------------- CSRF (S2)
def test_csrf_is_enforced(tmp_path):
    from app import create_app
    from app.extensions import db as _db
    app = create_app("testing", instance_path=tmp_path / "csrf", WTF_CSRF_ENABLED=True)
    with app.app_context():
        _db.create_all()
        res = app.test_client().post("/login-page", data={"email": "a@b.co", "password": "x"})
        assert res.status_code == 400 and b"Session expired" in res.data
        _db.drop_all()


def test_jobs_status_endpoint(logged_in):
    data = logged_in.get("/status/jobs").get_json()
    assert set(data) == {"home_feed", "news_feed"} and data["home_feed"]["due"] is True


def test_missing_spotify_id_is_filled_in(client, fake_sp, offline, monkeypatch, db):
    import app.services.catalog as catalog
    monkeypatch.setattr(catalog, "new_releases", lambda limit=10: [])
    user = make_user()
    user.spotify_user_id = None
    db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
    assert client.get("/playlist").status_code == 200
    assert user.spotify_user_id == "me"


@pytest.mark.parametrize("url", ["/", "/see-whats-new-results?keyword=hot-100", f"/song-page/{SPOTIFY_ID}", "/suggested-songs"])
def test_pages_never_download_audio_on_load(client, db, offline, catalog_client, url):
    """Previews are buttons with data-preview; no <audio> or audio src that a browser would fetch."""
    import re
    db.session.add(SchedulerStatus(job_name=tasks.HOME_JOB, last_run=datetime.now(timezone.utc)))
    db.session.add(HomeData(album_name="X", top_albums=[], best_2025_hits=[], artist_section_dict={},
                            this_weeks_hits=[{"name": "S", "artist": "A", "image": None, "spotify_song_id": "s1",
                                              "preview_url": "https://audio.example/p.m4a"}],
                            feature_artists_info={"artist_name": "A"},
                            top_artist_album_track=[{"id": "t", "name": "T", "preview_url": "https://audio.example/q.m4a"}]))
    db.session.commit()
    html = client.get(url).get_data(as_text=True)
    assert "<audio" not in html
    assert not re.search(r'(src|href)="[^"]+\.(m4a|mp3|aac)"', html)
    if url == "/":
        assert 'data-preview="https://audio.example/p.m4a"' in html



# --------------------------------------------------------------------- article page & comments
def test_comment_plain_text_becomes_paragraphs(logged_in, post):
    text = "\n".join(["First line", "same paragraph", "", "Second paragraph"])
    logged_in.post("/blog-post/7", data={"comment_text": text})
    assert Comment.query.one().text == "<p>First line<br>same paragraph</p><p>Second paragraph</p>"


def test_comment_validation(logged_in, post):
    res = logged_in.post("/blog-post/7", data={"comment_text": "x"})
    assert res.status_code == 400 and Comment.query.count() == 0
    res = logged_in.post("/blog-post/7", data={"comment_text": "y" * 2001})
    assert res.status_code == 400 and Comment.query.count() == 0


def test_new_comment_redirects_to_its_anchor(logged_in, post):
    res = logged_in.post("/blog-post/7", data={"comment_text": "Great read"})
    assert res.headers["Location"].endswith(f"#comment-{Comment.query.one().id}")


def test_edit_own_comment(logged_in, user, post, db):
    comment = Comment(text="<p>old</p>", author_id=user.id, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    page = logged_in.get("/blog-post/7").get_data(as_text=True)
    assert "class=\"ss-edit-form\"" in page and "You</span>" in page
    logged_in.post(f"/comments/{comment.id}/edit", data={"comment_text": "new text"})
    assert comment.text == "<p>new text</p>" and comment.edited_at is not None
    assert "edited" in logged_in.get("/blog-post/7").get_data(as_text=True)


def test_cannot_edit_someone_elses_comment(client, post, db):
    author, other = make_user(), make_user("other@example.com")
    comment = Comment(text="<p>mine</p>", author_id=author.id, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(other.id)
    assert client.post(f"/comments/{comment.id}/edit", data={"comment_text": "hacked"}).status_code == 403
    assert comment.text == "<p>mine</p>"
    assert "class=\"ss-edit-form\"" not in client.get("/blog-post/7").get_data(as_text=True)


def test_comments_sort_and_anonymous_prompt(client, post, db):
    from datetime import timedelta
    user = make_user()
    base = datetime(2026, 1, 1)
    for i, text in enumerate(["first", "second"]):
        db.session.add(Comment(text=f"<p>{text}</p>", author_id=user.id, post_id=post.id,
                               created_at=base + timedelta(hours=i)))
    db.session.commit()
    oldest = client.get("/blog-post/7").get_data(as_text=True)
    newest = client.get("/blog-post/7?sort=newest").get_data(as_text=True)
    assert oldest.index("<p>first</p>") < oldest.index("<p>second</p>")
    assert newest.index("<p>second</p>") < newest.index("<p>first</p>")
    assert "Join the conversation" in oldest and "comment_text" not in oldest      # no composer when logged out


def test_article_page_shows_details_and_source_link(client, db):
    p = BlogPost(title="Big news", subtitle="Short dek", body="<p>Excerpt text.</p>", created_id=8, day=2, month="Nov",
                 year=2026, news_link="https://billboard.com/a", source="Billboard", byline="Jane Doe",
                 tags=["Rock", "Tour"], img_url="https://img/cover.jpg", date=datetime(2026, 11, 2))
    db.session.add(p)
    db.session.commit()
    html = client.get("/blog-post/8").get_data(as_text=True)
    for needle in ("Jane Doe", "Rock", "Read the full story", "https://img/cover.jpg", "min read", "og:title"):
        assert needle in html, needle
