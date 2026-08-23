"""align regions columns with CSV source

Revision ID: 0b7c9d1e2f34
Revises: f1e2d3c4b5a6
Create Date: 2026-08-23 22:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography


# revision identifiers, used by Alembic.
revision: str = "0b7c9d1e2f34"
down_revision: Union[str, Sequence[str], None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("fk_regions_parent_region_id_regions", "regions", type_="foreignkey")
    op.drop_constraint("uq_regions_parent_name", "regions", type_="unique")

    op.alter_column("regions", "parent_region_id", new_column_name="parent_id")
    op.alter_column("regions", "bjd_cd", existing_type=sa.String(length=10), nullable=False)
    op.alter_column("regions", "boundary", nullable=False)

    op.drop_column("regions", "area_code")
    op.drop_column("regions", "sigungu_code")
    op.drop_column("regions", "centroid")

    op.create_unique_constraint(
        "uq_regions_parent_name",
        "regions",
        ["parent_id", "name"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_foreign_key(
        "fk_regions_parent_id_regions",
        "regions",
        "regions",
        ["parent_id"],
        ["region_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_regions_parent_id_regions", "regions", type_="foreignkey")
    op.drop_constraint("uq_regions_parent_name", "regions", type_="unique")

    op.add_column(
        "regions",
        sa.Column(
            "centroid",
            Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
    )
    op.add_column("regions", sa.Column("sigungu_code", sa.String(length=10), nullable=True))
    op.add_column("regions", sa.Column("area_code", sa.String(length=10), nullable=True))

    op.alter_column("regions", "boundary", nullable=True)
    op.alter_column("regions", "bjd_cd", existing_type=sa.String(length=10), nullable=True)
    op.alter_column("regions", "parent_id", new_column_name="parent_region_id")

    op.create_unique_constraint(
        "uq_regions_parent_name",
        "regions",
        ["parent_region_id", "name"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_foreign_key(
        "fk_regions_parent_region_id_regions",
        "regions",
        "regions",
        ["parent_region_id"],
        ["region_id"],
        ondelete="CASCADE",
    )
