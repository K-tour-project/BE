"""Store filming relations by product and place IDs."""
from alembic import op
import sqlalchemy as sa

revision = "b4c6d8e0f2a1"
down_revision = "a3f9c6d2e7b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_places",
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("place_id", sa.BigInteger(), sa.ForeignKey("places.place_id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_product_places_place_id", "product_places", ["place_id"])
    # A title shared by several products cannot identify the intended product.
    op.execute("""
        INSERT INTO product_places (product_id, place_id)
        SELECT min(pr.product_id), p.place_id
        FROM places p
        JOIN products pr ON pr.title = p.title
        WHERE p.title IS NOT NULL
          AND (SELECT count(*) FROM products matching WHERE matching.title = p.title) = 1
        GROUP BY p.place_id
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_product_places_place_id", table_name="product_places")
    op.drop_table("product_places")
