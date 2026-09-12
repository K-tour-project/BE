"""Add per-user profile image URLs; restore the previously applied revision."""
from alembic import op
import sqlalchemy as sa

revision = "d4e6f8a0b2c3"
down_revision = "c6d8e0a2b4f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_image_url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name=op.f("fk_user_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")
