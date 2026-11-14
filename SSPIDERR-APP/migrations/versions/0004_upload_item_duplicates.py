"""Mark recognised songs that were skipped because they were already in the playlist.

Before this, duplicates were stored as added=True. For finished jobs whose
summary says "added 0 new songs", every "added" item was in fact a duplicate,
so those rows are corrected. Other old jobs can't be told apart and are left as they are.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("upload_job_items") as batch:
        batch.add_column(sa.Column("already_in_playlist", sa.Boolean(), nullable=True))
    op.execute("""
        UPDATE upload_job_items
           SET already_in_playlist = 1, added = NULL
         WHERE added = 1
           AND job_id IN (SELECT id FROM upload_jobs WHERE state = 'done' AND message LIKE '%added 0 new song%')
    """)


def downgrade():
    op.execute("UPDATE upload_job_items SET added = 1 WHERE already_in_playlist = 1")
    with op.batch_alter_table("upload_job_items") as batch:
        batch.drop_column("already_in_playlist")
