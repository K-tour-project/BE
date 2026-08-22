"""add regions boundary geometry

Revision ID: a8f8b2f6d3c1
Revises: c4d4fdb425b1
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = "a8f8b2f6d3c1"
down_revision: Union[str, Sequence[str], None] = "c4d4fdb425b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "regions",
        sa.Column(
            "boundary",
            Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_regions_boundary",
        "regions",
        ["boundary"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_regions_boundary", table_name="regions")
    op.drop_column("regions", "boundary")
