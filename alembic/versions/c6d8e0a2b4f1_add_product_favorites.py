"""Merge catalog/place-favorite histories and add product favorites.

Restored from the previously applied migration. Review upstream migrations before
upgrading an older database; some ancestors remove legacy contents.
"""
from alembic import op
import sqlalchemy as sa

revision = "c6d8e0a2b4f1"
down_revision = ("b23c45d67e89", "b7e3a91f2046")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_favorites",
        sa.Column("favorite_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name=op.f("fk_product_favorites_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], name=op.f("fk_product_favorites_product_id_products"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("favorite_id", name=op.f("pk_product_favorites")),
        sa.UniqueConstraint("user_id", "product_id", name="uq_product_favorites_user_product"),
    )
    op.create_index("ix_product_favorites_user_created", "product_favorites", ["user_id", "created_at", "favorite_id"])
    op.create_index("ix_product_favorites_product_id", "product_favorites", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_favorites_product_id", table_name="product_favorites")
    op.drop_index("ix_product_favorites_user_created", table_name="product_favorites")
    op.drop_table("product_favorites")
