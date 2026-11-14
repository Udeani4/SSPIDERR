"""Home-feed builder and news refresh."""
from datetime import datetime

import pytest

from app.models import BlogPost, Comment, HomeData
from app.services import home_feed, news


@pytest.fixture
def sources(monkeypatch, offline):
    monkeypatch.setattr(home_feed, "top_albums", lambda limit=10: [
        {"album_name": "GNX", "artist_name": "Kendrick", "album_id": 111, "artwork_full": "http://a/1000"}])
    monkeypatch.setattr(home_feed, "top_songs", lambda limit=10: [
        {"song_name": "Luther", "song_id": 222, "artist_name": "Kendrick", "artwork_url_original": "http://s"}])
    monkeypatch.setattr(home_feed, "top_artists", lambda limit=10: ["Kendrick", "SZA"])
    monkeypatch.setattr(home_feed.catalog, "playlist_preview", lambda pid, limit=15: [{"name": "x", "id": "1"}] * 12)
    monkeypatch.setattr(home_feed, "global_top_tracks", lambda limit=10: [{"name": "y"}] * 10)
    monkeypatch.setattr(home_feed.catalog, "artist_profile", lambda name: {"artist_name": name, "album_id": "al"})
    monkeypatch.setattr(home_feed.catalog, "album_tracks_sorted", lambda album_id: [{"id": "t", "name": "best"}])


def test_build_home_snapshot(app, sources):
    data = home_feed.build_home_snapshot()
    assert data["album_name"] == "GNX" and data["album_id"] == "111"
    assert data["song_id"] == "222" and data["artist_name"] == "Kendrick"
    assert len(data["best_2025_hits"]) == 10 and len(data["this_weeks_hits"]) == 10
    assert set(data["artist_section_dict"]) == {"Kendrick", "SZA"}
    assert data["top_artist_album_track"][0]["name"] == "best"


def test_build_home_snapshot_survives_partial_failures(app, sources, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(home_feed, "global_top_tracks", boom)
    monkeypatch.setattr(home_feed.catalog, "artist_profile", boom)
    data = home_feed.build_home_snapshot()                          # B6: one bad source != broken page
    assert data["this_weeks_hits"] == [] and data["feature_artists_info"] == {}
    assert data["album_name"] == "GNX"


def test_build_home_snapshot_raises_when_everything_fails(app, sources, monkeypatch):
    for name in ("top_albums", "top_songs", "top_artists"):
        monkeypatch.setattr(home_feed, name, lambda limit=10: [])
    with pytest.raises(RuntimeError):
        home_feed.build_home_snapshot()


def test_save_snapshot_keeps_only_recent_rows(app, db):
    for i in range(6):
        home_feed.save_snapshot({"album_name": f"v{i}", "top_albums": []})
    assert HomeData.query.count() == home_feed.KEEP_SNAPSHOTS
    assert home_feed.latest_snapshot().album_name == "v5"


# --------------------------------------------------------------------- news
def test_date_parts_falls_back_to_now():
    when, day, month, year = news._date_parts("not a date")          # B15
    assert isinstance(when, datetime) and year >= 2026 and len(month) == 3


def test_refresh_news_dedupes_sanitises_and_trims(app, db, monkeypatch):
    articles = [news._article("Billboard", f"Story {i}", f"<p>Desc {i}</p><script>x()</script>", None,
                              f"https://news/{i}", f"2026-11-{(i % 28) + 1:02d}T10:00:00Z", None) for i in range(10)]
    monkeypatch.setattr(news, "fetch_newsdata_news", lambda: articles[:6])
    monkeypatch.setattr(news, "fetch_billboard_news", lambda: articles[4:])        # 2 duplicates
    app.config["NEWS_KEEP_LATEST"] = 5

    # An old post with a comment must survive trimming.
    old = BlogPost(title="Old", body="b", created_id=1, day=1, month="Jan", year=2020, date=datetime(2020, 1, 1),
                   news_link="https://old")
    db.session.add(old)
    db.session.commit()
    db.session.add(Comment(text="keep me", post_id=old.id))
    db.session.commit()

    assert news.refresh_news() == 10
    links = {p.news_link for p in BlogPost.query}
    assert "https://old" in links and len(links) == 6
    assert all("<script" not in (p.subtitle or "") for p in BlogPost.query)
    assert len({p.created_id for p in BlogPost.query}) == BlogPost.query.count()


def test_refresh_news_raises_when_no_source_works(app, monkeypatch):
    monkeypatch.setattr(news, "fetch_newsdata_news", lambda: [])
    monkeypatch.setattr(news, "fetch_billboard_news", lambda: [])
    with pytest.raises(RuntimeError):
        news.refresh_news()
