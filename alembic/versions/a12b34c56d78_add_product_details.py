"""Preserve products and backfill optional category details."""
from alembic import op
import sqlalchemy as sa

revision = "a12b34c56d78"
down_revision = "f8c2d6a0b4e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("product_category", "products", type_="check")
    op.execute("UPDATE products SET category = CASE WHEN category = '영화' THEN 'MOVIE' ELSE 'DRAMA' END")
    op.create_check_constraint("product_category", "products", "category IN ('MOVIE', 'DRAMA')")
    op.create_table(
        "movie_details",
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True, autoincrement=False),
        sa.Column("tmdb_id", sa.BigInteger(), unique=True),
        sa.Column("runtime", sa.Integer()),
    )
    op.create_table(
        "drama_details",
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True, autoincrement=False),
        sa.Column("overview_translated", sa.Boolean()),
        sa.Column("content_type", sa.Text()),
        sa.Column("networks", sa.Text()),
        sa.Column("episode_count", sa.Integer()),
        sa.Column("cast", sa.Text()),
    )
    op.execute('''INSERT INTO drama_details
        (product_id, overview_translated, content_type, networks, episode_count, "cast")
        SELECT product_id, is_overview_translated, product_type, networks, episode_count, lead_actors
        FROM products WHERE category = 'DRAMA' ''')


def downgrade() -> None:
    # Copy current drama values back before removing the detail tables.
    op.execute('''UPDATE products p SET is_overview_translated = d.overview_translated,
        product_type = d.content_type, networks = d.networks,
        episode_count = d.episode_count, lead_actors = d."cast"
        FROM drama_details d WHERE p.product_id = d.product_id''')
    op.drop_table("drama_details")
    op.drop_table("movie_details")
    op.drop_constraint("product_category", "products", type_="check")
    op.execute("UPDATE products SET category = CASE WHEN category = 'MOVIE' THEN '영화' ELSE '드라마' END")
    op.create_check_constraint("product_category", "products", "category IN ('영화', '드라마')")
