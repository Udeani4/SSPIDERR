"""Article byline/tags and comment edit time.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("blog_posts") as batch:
        batch.add_column(sa.Column("byline", sa.String(200), nullable=True))
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=True))
    with op.batch_alter_table("comments") as batch:
        batch.add_column(sa.Column("edited_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("comments") as batch:
        batch.drop_column("edited_at")
    with op.batch_alter_table("blog_posts") as batch:
        batch.drop_column("tags")
        batch.drop_column("byline")
