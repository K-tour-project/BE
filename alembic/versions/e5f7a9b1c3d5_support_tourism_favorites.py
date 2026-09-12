"""Allow favorites for TourAPI attractions without a local filming location."""
from alembic import op
import sqlalchemy as sa

revision = "e5f7a9b1c3d5"
down_revision = "d4e6f8a0b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("favorites", sa.Column("tour_content_id", sa.String(20), nullable=True))
    op.alter_column("favorites", "place_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_unique_constraint("uq_favorites_user_tour_content", "favorites", ["user_id", "tour_content_id"])
    op.create_check_constraint("favorite_has_target", "favorites", "place_id IS NOT NULL OR tour_content_id IS NOT NULL")


def downgrade() -> None:
    # A tourism-only favorite cannot be represented by the previous schema.
    # Require explicit data handling rather than silently deleting saved places.
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM favorites WHERE place_id IS NULL)")):
        raise ValueError("Tourism-only favorites exist; preserve or remove them explicitly before downgrade.")
    op.drop_constraint("favorite_has_target", "favorites", type_="check")
    op.drop_constraint("uq_favorites_user_tour_content", "favorites", type_="unique")
    op.alter_column("favorites", "place_id", existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("favorites", "tour_content_id")
