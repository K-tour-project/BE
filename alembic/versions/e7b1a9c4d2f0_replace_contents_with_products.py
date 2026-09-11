"""Remove the empty legacy contents model in favor of products.

Revision ID: e7b1a9c4d2f0
Revises: d2e4f6a8b0c1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e7b1a9c4d2f0"
down_revision = "d2e4f6a8b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("content_place_mappings")
    op.drop_table("contents")
    op.execute("DROP TYPE IF EXISTS content_type")


def downgrade() -> None:
    content_type = postgresql.ENUM("movie", "drama", "show", name="content_type")
    content_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "contents",
        sa.Column("content_id", sa.BigInteger(), primary_key=True),
        sa.Column("content_type", content_type, nullable=False),
        sa.Column("title_ko", sa.String(200), nullable=False),
        sa.Column("poster_url", sa.Text()),
        sa.Column("kmdb_code", sa.String(20), unique=True),
        sa.Column("source", sa.String(20)),
        sa.Column("source_url", sa.Text()),
        sa.Column("production_year", sa.Integer()),
        sa.Column("original_title", sa.String(300)),
        sa.Column("overview", sa.Text()),
        sa.Column("genre_tags", postgresql.ARRAY(sa.String(50))),
        sa.Column("tmdb_id", sa.Integer()),
        sa.Column("tmdb_type", sa.String(10)),
        sa.Column("vote_average", sa.Numeric(3, 1)),
        sa.Column("runtime", sa.Integer()),
    )
    op.create_index("ix_contents_genre_tags", "contents", ["genre_tags"], postgresql_using="gin")
    op.create_table(
        "content_place_mappings",
        sa.Column("mapping_id", sa.BigInteger(), primary_key=True),
        sa.Column("content_id", sa.BigInteger(), sa.ForeignKey("contents.content_id", ondelete="CASCADE"), nullable=False),
        sa.Column("place_id", sa.BigInteger(), sa.ForeignKey("places.place_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kmdb_case_id", sa.String(40), unique=True),
        sa.Column("scene_description", sa.Text()),
        sa.Column("characters", sa.String(300)),
        sa.Column("episode", sa.String(50)),
        sa.UniqueConstraint("content_id", "place_id", name="uq_cpm_content_place"),
    )
    op.create_index("ix_cpm_place_id", "content_place_mappings", ["place_id"])
