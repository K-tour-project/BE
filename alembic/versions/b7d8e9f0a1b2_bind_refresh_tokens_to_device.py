"""bind refresh tokens to device

Revision ID: b7d8e9f0a1b2
Revises: 0b7c9d1e2f34, 9a1c7d2e5b40
Create Date: 2026-09-03 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = (
    "0b7c9d1e2f34",
    "9a1c7d2e5b40",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "device_id_hash",
            sa.String(length=64),
            nullable=False,
            server_default="0000000000000000000000000000000000000000000000000000000000000000",
        ),
    )
    op.alter_column("refresh_tokens", "device_id_hash", server_default=None)
    op.create_index(
        "ix_refresh_tokens_user_device",
        "refresh_tokens",
        ["user_id", "device_id_hash"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_refresh_tokens_user_device", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "device_id_hash")
