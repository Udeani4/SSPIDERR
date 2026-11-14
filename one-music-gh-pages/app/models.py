"""Database models.

Schema changes go through Flask-Migrate:  `flask --app run db migrate -m "..."`
then `flask --app run db upgrade`.  Never drop tables by hand (A6).
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "sspiderr_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(255))
    spotify_acc_tok: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    spotify_ref_tok: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    spotify_user_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    # Unix timestamp; lets us refresh the token only when it is about to expire (B12).
    spotify_token_expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")
    review_comments = relationship("ReviewComment", back_populates="review_author")

    @property
    def display_name(self):
        return (self.email or "user").split("@")[0]

    @property
    def has_spotify(self):
        return bool(self.spotify_ref_tok)


class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    subtitle: Mapped[str | None] = mapped_column(String(250), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str | None] = mapped_column(String(250), nullable=True)
    source: Mapped[str | None] = mapped_column(String(250), nullable=True)
    news_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Public id used in /blog-post/<created_id> URLs.
    created_id: Mapped[int] = mapped_column(Integer, unique=True)
    day: Mapped[int] = mapped_column(Integer)
    month: Mapped[str] = mapped_column(String(10))   # "Oct" etc.
    year: Mapped[int] = mapped_column(Integer)
    author_id = mapped_column(Integer, ForeignKey("sspiderr_users.id"), nullable=True)

    author = relationship("User", back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="parent_post", cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )


class Comment(db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    author_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sspiderr_users.id", ondelete="SET NULL"), nullable=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False)

    comment_author: Mapped["User"] = relationship("User", back_populates="comments")
    parent_post: Mapped["BlogPost"] = relationship("BlogPost", back_populates="comments")


class ReviewComment(db.Model):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.now())
    author_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sspiderr_users.id", ondelete="SET NULL"), nullable=True)

    review_author: Mapped["User"] = relationship("User", back_populates="review_comments")


class Playlist(db.Model):
    """Local mirror of a user's Spotify playlists (names + snapshot ids)."""
    __tablename__ = "user_playlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    spotify_playlist_id: Mapped[str] = mapped_column(String(50), index=True)
    spotify_user_id: Mapped[str] = mapped_column(String(50), index=True)
    # Spotify changes snapshot_id whenever the playlist changes; lets us skip
    # re-downloading playlists that haven't changed (P11).
    snapshot_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Songs(db.Model):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    album: Mapped[str] = mapped_column(String(100))
    artist: Mapped[str] = mapped_column(String(100))
    duration_ms: Mapped[int] = mapped_column(Integer)
    popularity: Mapped[int] = mapped_column(Integer)
    preview_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    external_url: Mapped[str] = mapped_column(String())
    spotify_playlist_id: Mapped[str] = mapped_column(String(50), index=True)
    spotify_user_id: Mapped[str] = mapped_column(String(50), index=True)


class HomeData(db.Model):
    """One snapshot of the (global) home-page feed. The newest row is shown."""
    __tablename__ = "home_data"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    album_id = mapped_column(String(100), nullable=True)
    album_art = mapped_column(String(500), nullable=True)
    album_name = mapped_column(String(255), nullable=True)
    song_art = mapped_column(String(500), nullable=True)
    song_name = mapped_column(String(255), nullable=True)
    song_id = mapped_column(String(100), nullable=True)
    artist_art = mapped_column(String(500), nullable=True)
    artist_name = mapped_column(String(255), nullable=True)

    top_albums = mapped_column(JSON, nullable=True)
    feature_artists_info = mapped_column(JSON, nullable=True)
    artist_description = mapped_column(JSON, nullable=True)
    top_artist_album_track = mapped_column(JSON, nullable=True)
    best_2025_hits = mapped_column(JSON, nullable=True)
    this_weeks_hits = mapped_column(JSON, nullable=True)
    artist_section_dict = mapped_column(JSON, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SchedulerStatus(db.Model):
    """Bookkeeping for each background job (see app/tasks.py).

    `last_run` is the last *successful* run. `should_run_24h_task()` decides
    from it whether the job's data is stale.
    """
    __tablename__ = "scheduler_status"

    id = mapped_column(Integer, primary_key=True)
    job_name = mapped_column(String(50), unique=True, nullable=False)
    last_run = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt = mapped_column(DateTime(timezone=True), nullable=True)
    last_error = mapped_column(Text, nullable=True)
    running_since = mapped_column(DateTime(timezone=True), nullable=True)


class UploadJob(db.Model):
    """One "recognise my uploads and add them to a playlist" run (A5)."""
    __tablename__ = "upload_jobs"

    id = mapped_column(Integer, primary_key=True)
    public_id = mapped_column(String(36), unique=True, nullable=False, index=True)
    user_id = mapped_column(Integer, ForeignKey("sspiderr_users.id", ondelete="CASCADE"), nullable=False, index=True)
    playlist_id = mapped_column(String(50), nullable=False)
    playlist_name = mapped_column(String(200), nullable=True)
    state = mapped_column(String(20), nullable=False, default="queued")   # queued|running|done|failed
    message = mapped_column(Text, nullable=True)
    last_event = mapped_column(String(30), nullable=True)   # recognized|not_recognized|sent|not_sent
    last_event_text = mapped_column(String(200), nullable=True)
    total_files = mapped_column(Integer, default=0)
    processed_files = mapped_column(Integer, default=0)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["UploadJobItem"]] = relationship(
        "UploadJobItem", back_populates="job", cascade="all, delete-orphan", order_by="UploadJobItem.id")

    @property
    def is_active(self):
        return self.state in {"queued", "running"}


class UploadJobItem(db.Model):
    __tablename__ = "upload_job_items"

    id = mapped_column(Integer, primary_key=True)
    job_id = mapped_column(Integer, ForeignKey("upload_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = mapped_column(String(255), nullable=False)
    title = mapped_column(String(300), nullable=True)
    artist = mapped_column(String(300), nullable=True)
    recognized = mapped_column(db.Boolean, nullable=True)
    spotify_uri = mapped_column(String(100), nullable=True)
    added = mapped_column(db.Boolean, nullable=True)
    error = mapped_column(Text, nullable=True)

    job = relationship("UploadJob", back_populates="items")
