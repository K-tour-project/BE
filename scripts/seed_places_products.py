"""Load CSVs atomically; identical rows are skipped on repeat runs.

Run: python -m scripts.seed_places_products [--dry-run]
Pipe-delimited genres/actors are retained as supplied in the CSV.
"""
import argparse
import asyncio
import csv
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from geoalchemy2 import WKTElement
from sqlalchemy.dialects.postgresql import insert

from app.core.db import AsyncSessionLocal, engine
from app.models import Place, Product

DATA = Path(__file__).resolve().parents[1] / "data"
PLACE_COLUMNS = {
    "제목": "title", "장소명": "name", "장소타입": "place_type",
    "주소": "address", "위도": "latitude", "경도": "longitude",
    "source_url": "source_url", "데이터출처": "source", "위치정보출처": "location_source",
}
PRODUCT_COLUMNS = {
    "제목": "title", "줄거리": "overview", "줄거리_번역여부": "is_overview_translated",
    "최초방영일": "first_air_date", "작품유형": "product_type", "포스터": "poster_url",
    "장르": "genres", "networks": "networks", "에피소드수": "episode_count",
    "평점": "rating", "인기도": "popularity", "주연배우": "lead_actors",
    "match_similarity": "match_similarity",
}


def load_rows(filename, columns):
    rows = []
    occurrences = {}
    with (DATA / filename).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != set(columns):
            raise ValueError(f"{filename}: unexpected CSV headers")
        for line, source in enumerate(reader, 2):
            try:
                row = {target: source[key].strip() or None for key, target in columns.items()}
                if not row["title"] or (filename == "places.csv" and not row["name"]):
                    raise ValueError("title/name must not be empty")
                payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
                # Preserve duplicate rows in the file while making repeat imports safe.
                occurrences[payload] = occurrences.get(payload, 0) + 1
                row["csv_row_hash"] = hashlib.sha256(
                    f"{payload}:{occurrences[payload]}".encode("utf-8")
                ).hexdigest()
                for key in ("latitude", "longitude", "rating", "popularity", "match_similarity"):
                    if row.get(key) is not None:
                        row[key] = Decimal(row[key])
                        if not row[key].is_finite():
                            raise ValueError(f"invalid {key}")
                if filename == "places.csv":
                    lat, lon = row["latitude"], row["longitude"]
                    if lat is not None and not -90 <= lat <= 90:
                        raise ValueError("invalid latitude")
                    if lon is not None and not -180 <= lon <= 180:
                        raise ValueError("invalid longitude")
                    row["geom"] = WKTElement(f"POINT({lon} {lat})", srid=4326) if lat is not None and lon is not None else None
                else:
                    if row["first_air_date"]:
                        row["first_air_date"] = date.fromisoformat(row["first_air_date"])
                    if row["episode_count"]:
                        row["episode_count"] = int(row["episode_count"])
                    if row["is_overview_translated"] is not None:
                        value = row["is_overview_translated"].upper()
                        if value not in ("TRUE", "FALSE"):
                            raise ValueError("invalid translation flag")
                        row["is_overview_translated"] = value == "TRUE"
                rows.append(row)
            except (ValueError, ArithmeticError, AttributeError) as exc:
                raise ValueError(f"{filename}: row {line}: {exc}") from exc
    return rows


async def seed(dry_run=False):
    batches = [(Place, load_rows("places.csv", PLACE_COLUMNS)),
               (Product, load_rows("products.csv", PRODUCT_COLUMNS))]
    for model, rows in batches:
        print(f"{model.__tablename__}: {len(rows)} CSV rows validated")
    if dry_run:
        return
    try:
        async with AsyncSessionLocal.begin() as session:
            for model, rows in batches:
                count = 0
                for offset in range(0, len(rows), 500):
                    result = await session.execute(
                        insert(model.__table__).values(rows[offset:offset + 500])
                        .on_conflict_do_nothing(index_elements=["csv_row_hash"])
                        .returning(list(model.__table__.primary_key.columns)[0])
                    )
                    count += len(result.all())
                print(f"{model.__tablename__}: {count} inserted")
        print("Commit complete")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(seed(parser.parse_args().dry_run))
