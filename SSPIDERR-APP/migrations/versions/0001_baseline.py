"""Baseline: the schema as it was before the 2026-11 refactor.

Existing databases are *stamped* at this revision (`flask --app main db stamp 0001`);
fresh installs create it with `flask --app main db upgrade`.

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

LOG_TABLES = ("recognised_songs", "unrecognised_songs", "sent_spotify_songs", "unsent_spotify_songs")


def upgrade():
    op.create_table(
        "sspiderr_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(100), nullable=False, unique=True),
        sa.Column("password", sa.String(100), nullable=False),
        sa.Column("spotify_acc_tok", sa.Text(), unique=True),
        sa.Column("spotify_ref_tok", sa.Text(), unique=True),
        sa.Column("spotify_user_id", sa.String(50), unique=True),
    )
    op.create_table(
        "user_playlist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("spotify_playlist_id", sa.String(50), nullable=False),
        sa.Column("spotify_user_id", sa.String(50), nullable=False),
    )
    for name in LOG_TABLES:
        op.create_table(
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("track", sa.String(500), nullable=False),
            sa.Column("spotify_playlist_id", sa.String(50), nullable=False),
            sa.Column("spotify_user_id", sa.String(50), nullable=False),
        )
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("subtitle", sa.String(250)),
        sa.Column("date", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("img_url", sa.String(250)),
        sa.Column("source", sa.String(250)),
        sa.Column("news_link", sa.String(1000)),
        sa.Column("created_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("sspiderr_users.id")),
    )
    op.create_index("ix_blog_posts_title", "blog_posts", ["title"])
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("sspiderr_users.id", ondelete="SET NULL")),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_table(
        "home_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("album_id", sa.BigInteger()),
        sa.Column("album_art", sa.String(500)),
        sa.Column("album_name", sa.String(255)),
        sa.Column("song_art", sa.String(500)),
        sa.Column("song_name", sa.String(255)),
        sa.Column("song_id", sa.String(100)),
        sa.Column("artist_art", sa.String(500)),
        sa.Column("artist_name", sa.String(255)),
        sa.Column("top_albums", sa.JSON()),
        sa.Column("feature_artists_info", sa.JSON()),
        sa.Column("artist_description", sa.JSON()),
        sa.Column("top_artist_album_track", sa.JSON()),
        sa.Column("best_2025_hits", sa.JSON()),
        sa.Column("this_weeks_hits", sa.JSON()),
        sa.Column("artist_section_dict", sa.JSON()),
        sa.Column("new_time_tag", sa.DateTime()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("sspiderr_users.id")),
    )
    op.create_table(
        "review_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("sspiderr_users.id", ondelete="SET NULL")),
    )
    op.create_table(
        "songs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("track_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("album", sa.String(100), nullable=False),
        sa.Column("artist", sa.String(100), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("popularity", sa.Integer(), nullable=False),
        sa.Column("preview_url", sa.String()),
        sa.Column("external_url", sa.String(), nullable=False),
        sa.Column("spotify_playlist_id", sa.String(50), nullable=False),
        sa.Column("spotify_user_id", sa.String(50), nullable=False),
    )
    op.create_table(
        "scheduler_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_run", sa.DateTime(), nullable=False),
        sa.Column("session_id", sa.String()),
        sa.Column("user_id", sa.String(50)),
    )


def downgrade():
    for name in ("scheduler_status", "songs", "review_comments", "home_data", "comments", "blog_posts",
                 *LOG_TABLES, "user_playlist", "sspiderr_users"):
        op.drop_table(name)
