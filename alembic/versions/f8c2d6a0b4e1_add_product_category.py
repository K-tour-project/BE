"""Persist the movie/drama category currently exposed by the API."""
from alembic import op
import sqlalchemy as sa

revision = "f8c2d6a0b4e1"
down_revision = "e7b1a9c4d2f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("category", sa.String(10), nullable=True))
    op.execute("""
        UPDATE products
        SET category = CASE
            WHEN lower(trim(product_type)) IN ('movie', 'film') THEN '영화'
            ELSE '드라마'
        END
    """)
    op.alter_column("products", "category", nullable=False)
    op.create_check_constraint("product_category", "products", "category IN ('영화', '드라마')")


def downgrade() -> None:
    op.drop_constraint("product_category", "products", type_="check")
    op.drop_column("products", "category")
