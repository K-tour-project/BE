"""Add products and preserve existing places while extending CSV fields."""
from alembic import op
import sqlalchemy as sa

revision = "d2e4f6a8b0c1"
down_revision = "b7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("title", "place_type", "source_url", "location_source"):
        op.add_column("places", sa.Column(name, sa.Text(), nullable=True))
    for name in ("latitude", "longitude"):
        op.add_column("places", sa.Column(name, sa.Numeric(10, 7), nullable=True))
    op.add_column("places", sa.Column("csv_row_hash", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_places_csv_row_hash", "places", ["csv_row_hash"])
    op.create_table(
        "products",
        sa.Column("product_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("overview", sa.Text()),
        sa.Column("is_overview_translated", sa.Boolean()),
        sa.Column("first_air_date", sa.Date()),
        sa.Column("product_type", sa.Text()),
        sa.Column("poster_url", sa.Text()),
        sa.Column("genres", sa.Text()),
        sa.Column("networks", sa.Text()),
        sa.Column("episode_count", sa.Integer()),
        sa.Column("rating", sa.Numeric()),
        sa.Column("popularity", sa.Numeric()),
        sa.Column("lead_actors", sa.Text()),
        sa.Column("match_similarity", sa.Numeric()),
        sa.Column("csv_row_hash", sa.String(64)),
        sa.UniqueConstraint("csv_row_hash", name="uq_products_csv_row_hash"),
    )


def downgrade():
    op.drop_table("products")
    op.drop_constraint("uq_places_csv_row_hash", "places", type_="unique")
    for name in ("csv_row_hash", "longitude", "latitude", "location_source", "source_url", "place_type", "title"):
        op.drop_column("places", name)
