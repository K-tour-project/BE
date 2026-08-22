"""Seed regions from data/regions.csv.

The CSV is the source of truth for the regions hierarchy and boundaries:
region_id, name, level, parent_id, boundary.

Run:
    python -m scripts.seed_regions
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import bindparam, text

from app.core.db import AsyncSessionLocal, engine


CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "regions.csv"
csv.field_size_limit(sys.maxsize)


def _read_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    required = {"region_id", "name", "level", "parent_id", "boundary"}
    missing = required.difference(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")

    normalized: list[dict] = []
    seen: set[int] = set()
    for row in rows:
        region_id = int(row["region_id"])
        if region_id in seen:
            raise ValueError(f"Duplicate region_id in CSV: {region_id}")
        seen.add(region_id)

        boundary = (row["boundary"] or "").strip()
        if not boundary:
            raise ValueError(f"Missing boundary for region_id={region_id}")

        parent_id = (row["parent_id"] or "").strip()
        normalized.append(
            {
                "region_id": region_id,
                "name": row["name"].strip(),
                "level": row["level"].strip(),
                "parent_region_id": int(parent_id) if parent_id else None,
                "boundary": boundary,
            }
        )

    return normalized


async def _upsert_regions(session, rows: list[dict]) -> None:
    stmt = text(
        """
        INSERT INTO regions (
            region_id,
            name,
            level,
            parent_region_id,
            boundary
        )
        VALUES (
            :region_id,
            :name,
            :level,
            :parent_region_id,
            ST_Multi(ST_GeomFromText(:boundary, 4326))
        )
        ON CONFLICT (region_id) DO UPDATE SET
            name = EXCLUDED.name,
            level = EXCLUDED.level,
            parent_region_id = EXCLUDED.parent_region_id,
            boundary = EXCLUDED.boundary
        """
    )

    level_1 = [row for row in rows if row["level"] == "1"]
    level_2 = [row for row in rows if row["level"] == "2"]
    other_levels = [row for row in rows if row["level"] not in {"1", "2"}]

    if other_levels:
        raise ValueError(
            "Unsupported levels in CSV: "
            + ", ".join(sorted({row["level"] for row in other_levels}))
        )

    await session.execute(stmt, level_1)
    await session.execute(stmt, level_2)


async def _prune_extra_regions(session, rows: list[dict]) -> int:
    region_ids = [row["region_id"] for row in rows]
    result = await session.execute(
        text("DELETE FROM regions WHERE region_id NOT IN :region_ids").bindparams(
            bindparam("region_ids", expanding=True)
        ),
        {"region_ids": region_ids},
    )
    return result.rowcount or 0


async def _validate(session, expected_count: int) -> dict[str, int]:
    checks = {
        "csv_rows": expected_count,
        "db_rows": (
            await session.execute(text("SELECT count(*) FROM regions"))
        ).scalar_one(),
        "null_boundaries": (
            await session.execute(
                text("SELECT count(*) FROM regions WHERE boundary IS NULL")
            )
        ).scalar_one(),
        "non_4326_boundaries": (
            await session.execute(
                text("SELECT count(*) FROM regions WHERE ST_SRID(boundary) <> 4326")
            )
        ).scalar_one(),
        "non_multipolygon_boundaries": (
            await session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM regions
                    WHERE GeometryType(boundary) <> 'MULTIPOLYGON'
                    """
                )
            )
        ).scalar_one(),
        "level_2_missing_parents": (
            await session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM regions child
                    LEFT JOIN regions parent
                      ON parent.region_id = child.parent_region_id
                    WHERE child.level = '2'
                      AND parent.region_id IS NULL
                    """
                )
            )
        ).scalar_one(),
    }
    return checks


async def seed(prune: bool = False) -> None:
    rows = _read_rows()

    async with AsyncSessionLocal() as session:
        await _upsert_regions(session, rows)
        pruned = await _prune_extra_regions(session, rows) if prune else 0
        checks = await _validate(session, len(rows))

        failed = {
            "db_rows": checks["db_rows"] != checks["csv_rows"],
            "null_boundaries": checks["null_boundaries"] != 0,
            "non_4326_boundaries": checks["non_4326_boundaries"] != 0,
            "non_multipolygon_boundaries": checks["non_multipolygon_boundaries"] != 0,
            "level_2_missing_parents": checks["level_2_missing_parents"] != 0,
        }

        if any(failed.values()):
            await session.rollback()
            print("Region seed validation failed:")
            for key, value in checks.items():
                print(f"  {key}: {value}")
            raise SystemExit(1)

        await session.commit()
        print(f"Seeded regions: {checks['db_rows']:,}")
        if prune:
            print(f"Pruned extra regions: {pruned:,}")
        print("Validation passed:")
        for key, value in checks.items():
            print(f"  {key}: {value}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete regions whose region_id is not present in data/regions.csv.",
    )
    args = parser.parse_args()
    asyncio.run(seed(prune=args.prune))


if __name__ == "__main__":
    main()
