"""Administrative regions and boundaries.

`data/regions.csv` is the source of truth:
region_id, parent_id, level, name, bjd_cd, boundary.
"""
from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Region(Base):
    __tablename__ = "regions"

    region_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.region_id", ondelete="CASCADE")
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    bjd_cd: Mapped[str] = mapped_column(String(10), nullable=False)
    boundary = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )

    parent: Mapped["Region | None"] = relationship(
        "Region", remote_side="Region.region_id", back_populates="children"
    )
    children: Mapped[list["Region"]] = relationship(
        "Region", back_populates="parent", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "parent_id",
            "name",
            name="uq_regions_parent_name",
            postgresql_nulls_not_distinct=True,
        ),
    )
