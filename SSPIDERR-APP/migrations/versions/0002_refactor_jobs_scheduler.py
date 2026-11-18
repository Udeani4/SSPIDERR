"""Refactor: token expiry, global home feed, job-based scheduler, upload jobs.

* sspiderr_users: + spotify_token_expires_at; password column widened (scrypt hashes are ~160 chars)
* user_playlist:  + snapshot_id, indexes
* songs:          indexes
* home_data:      one global feed -> drop user_id / new_time_tag, + created_at
* scheduler_status: rebuilt as one row per background job (old per-visitor rows are meaningless)
* recognised/unrecognised/sent/unsent_spotify_songs -> replaced by upload_jobs + upload_job_items
* blog_posts.month holds "Oct" etc. -> VARCHAR

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

LOG_TABLES = ("recognised_songs", "unrecognised_songs", "sent_spotify_songs", "unsent_spotify_songs")


def upgrade():
    with op.batch_alter_table("sspiderr_users") as batch:
        batch.add_column(sa.Column("spotify_token_expires_at", sa.Integer(), nullable=True))
        batch.alter_column("password", type_=sa.String(255), existing_type=sa.String(100), existing_nullable=False)

    with op.batch_alter_table("user_playlist") as batch:
        batch.add_column(sa.Column("snapshot_id", sa.String(100), nullable=True))
        batch.create_index("ix_user_playlist_spotify_playlist_id", ["spotify_playlist_id"])
        batch.create_index("ix_user_playlist_spotify_user_id", ["spotify_user_id"])

    with op.batch_alter_table("songs") as batch:
        batch.create_index("ix_songs_spotify_playlist_id", ["spotify_playlist_id"])
        batch.create_index("ix_songs_spotify_user_id", ["spotify_user_id"])

    with op.batch_alter_table("home_data") as batch:
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                                   server_default=sa.func.now()))
        batch.drop_column("user_id")
        batch.drop_column("new_time_tag")
        batch.alter_column("album_id", type_=sa.String(100), existing_type=sa.BigInteger())

    with op.batch_alter_table("blog_posts") as batch:
        batch.alter_column("month", type_=sa.String(10), existing_type=sa.Integer(), existing_nullable=False)

    op.drop_table("scheduler_status")
    op.create_table(
        "scheduler_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(50), nullable=False, unique=True),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("running_since", sa.DateTime(timezone=True), nullable=True),
    )

    for name in LOG_TABLES:
        op.drop_table(name)

    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("sspiderr_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("playlist_id", sa.String(50), nullable=False),
        sa.Column("playlist_name", sa.String(200), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("last_event", sa.String(30), nullable=True),
        sa.Column("last_event_text", sa.String(200), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=True),
        sa.Column("processed_files", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_upload_jobs_public_id", "upload_jobs", ["public_id"], unique=True)
    op.create_index("ix_upload_jobs_user_id", "upload_jobs", ["user_id"])
    op.create_table(
        "upload_job_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("upload_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("artist", sa.String(300), nullable=True),
        sa.Column("recognized", sa.Boolean(), nullable=True),
        sa.Column("spotify_uri", sa.String(100), nullable=True),
        sa.Column("added", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_upload_job_items_job_id", "upload_job_items", ["job_id"])


def downgrade():
    op.drop_index("ix_upload_job_items_job_id", "upload_job_items")
    op.drop_table("upload_job_items")
    op.drop_index("ix_upload_jobs_user_id", "upload_jobs")
    op.drop_index("ix_upload_jobs_public_id", "upload_jobs")
    op.drop_table("upload_jobs")
    for name in LOG_TABLES:
        op.create_table(
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("track", sa.String(500), nullable=False),
            sa.Column("spotify_playlist_id", sa.String(50), nullable=False),
            sa.Column("spotify_user_id", sa.String(50), nullable=False),
        )
    op.drop_table("scheduler_status")
    op.create_table(
        "scheduler_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_run", sa.DateTime(), nullable=False),
        sa.Column("session_id", sa.String()),
        sa.Column("user_id", sa.String(50)),
    )
    with op.batch_alter_table("blog_posts") as batch:
        batch.alter_column("month", type_=sa.Integer(), existing_type=sa.String(10), existing_nullable=False,
                           postgresql_using="EXTRACT(MONTH FROM date)::integer")
    with op.batch_alter_table("home_data") as batch:
        batch.alter_column("album_id", type_=sa.BigInteger(), existing_type=sa.String(100),
                           postgresql_using="NULLIF(regexp_replace(album_id, '[^0-9]', '', 'g'), '')::bigint")
        batch.add_column(sa.Column("new_time_tag", sa.DateTime()))
        batch.add_column(sa.Column("user_id", sa.Integer()))
        batch.drop_column("created_at")
    with op.batch_alter_table("songs") as batch:
        batch.drop_index("ix_songs_spotify_user_id")
        batch.drop_index("ix_songs_spotify_playlist_id")
    with op.batch_alter_table("user_playlist") as batch:
        batch.drop_index("ix_user_playlist_spotify_user_id")
        batch.drop_index("ix_user_playlist_spotify_playlist_id")
        batch.drop_column("snapshot_id")
    with op.batch_alter_table("sspiderr_users") as batch:
        batch.alter_column("password", type_=sa.String(100), existing_type=sa.String(255), existing_nullable=False)
        batch.drop_column("spotify_token_expires_at")
