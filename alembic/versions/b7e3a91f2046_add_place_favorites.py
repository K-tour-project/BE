"""Add place favorites (restored from the previously applied migration)."""
from alembic import op
import sqlalchemy as sa

revision = "b7e3a91f2046"
down_revision = "9a1c7d2e5b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("favorite_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("place_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name=op.f("fk_favorites_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_id"], ["places.place_id"], name=op.f("fk_favorites_place_id_places"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("favorite_id", name=op.f("pk_favorites")),
        sa.UniqueConstraint("user_id", "place_id", name="uq_favorites_user_place"),
    )
    op.create_index("ix_favorites_user_created", "favorites", ["user_id", "created_at", "favorite_id"])
    op.create_index("ix_favorites_place_id", "favorites", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_place_id", table_name="favorites")
    op.drop_index("ix_favorites_user_created", table_name="favorites")
    op.drop_table("favorites")
