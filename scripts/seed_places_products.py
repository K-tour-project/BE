"""Import separate CSVs atomically without deleting existing rows."""
import argparse
import asyncio
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from geoalchemy2 import WKTElement
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from app.core.db import AsyncSessionLocal, engine
from app.models import (
    CoursePlace, DramaDetail, MovieDetail, Place, PlaceFavorite, Product,
    ProductFavorite,
)

DATA = Path(__file__).resolve().parents[1] / "data"
PLACE_COLUMNS = {
    "제목": "title", "장소명": "name", "주소": "address", "위도": "latitude",
    "경도": "longitude", "source_url": "source_url", "데이터출처": "source",
    "위치정보출처": "location_source",
}
MOVIE_COLUMNS = {
    "title": "title", "overview": "overview", "release_date": "first_air_date",
    "genres": "genres", "poster": "poster_url", "vote_average": "rating",
    "popularity": "popularity", "category": "category", "runtime": "runtime",
}
DRAMA_COLUMNS = {
    "제목": "title", "줄거리": "overview", "최초방영일": "first_air_date",
    "장르": "genres", "포스터": "poster_url", "평점": "rating", "인기도": "popularity",
    "카테고리": "category", "줄거리_번역여부": "overview_translated",
    "작품유형": "content_type", "networks": "networks", "에피소드수": "episode_count", "주연배우": "cast",
}


def row_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def product_identity(row):
    return (row["category"], row["title"], row["first_air_date"])


def place_identity(row):
    return tuple(row.get(k) for k in ("title", "name", "source", "address", "source_url", "latitude", "longitude"))


def load_rows(filename, columns):
    rows = {}
    with (DATA / filename).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        # Accept and ignore the old external ID during the CSV transition.
        optional = {"장소유형"} if filename == "places.csv" else {"tmdb_id"}
        if not set(columns).issubset(headers) or set(headers) - set(columns) - optional:
            raise ValueError(f"{filename}: unexpected CSV headers: {headers}")
        for line, source in enumerate(reader, 2):
            try:
                if None in source or any(v is None for v in source.values()):
                    raise ValueError("incorrect number of columns")
                row = {target: source[key].strip() or None for key, target in columns.items()}
                if not row["title"]:
                    raise ValueError("title must not be empty")
                for key in ("latitude", "longitude", "rating", "popularity"):
                    if row.get(key) is not None:
                        row[key] = Decimal(row[key])
                        if not row[key].is_finite():
                            raise ValueError(f"invalid {key}")
                        if key in ("latitude", "longitude"):
                            row[key] = row[key].quantize(Decimal("0.0000001"))
                if filename == "places.csv":
                    if not row["name"]:
                        raise ValueError("name must not be empty")
                    if "장소유형" in source:
                        row["place_type"] = source["장소유형"].strip() or None
                    lat, lon = row["latitude"], row["longitude"]
                    if lat is not None and not -90 <= lat <= 90:
                        raise ValueError("invalid latitude")
                    if lon is not None and not -180 <= lon <= 180:
                        raise ValueError("invalid longitude")
                    identity = place_identity(row)
                else:
                    expected = "MOVIE" if filename == "products_movie.csv" else "DRAMA"
                    if row["category"] != expected:
                        raise ValueError(f"category must be {expected}")
                    if row["first_air_date"]:
                        row["first_air_date"] = date.fromisoformat(row["first_air_date"])
                    row["genres"] = "|".join(dict.fromkeys(
                        p.strip() for p in (row["genres"] or "").replace(",", "|").split("|") if p.strip()
                    )) or None
                    for key in ("runtime", "episode_count"):
                        if row.get(key) is not None:
                            row[key] = int(row[key])
                            if row[key] < 0:
                                raise ValueError(f"negative {key}")
                    if row.get("overview_translated") is not None:
                        value = row["overview_translated"].upper()
                        if value not in ("TRUE", "FALSE"):
                            raise ValueError("invalid translation flag")
                        row["overview_translated"] = value == "TRUE"
                    identity = product_identity(row)
                if identity in rows and rows[identity] != row:
                    raise ValueError(f"conflicting duplicate identity: {identity}")
                rows[identity] = row
            except (ValueError, ArithmeticError, AttributeError) as exc:
                raise ValueError(f"{filename}: row {line}: {exc}") from exc
    return list(rows.values())


async def import_products(session, rows):
    counts = Counter()
    for row in rows:
        model = MovieDetail if row["category"] == "MOVIE" else DramaDetail
        fields = {c.name for c in model.__table__.columns} - {"product_id"}
        detail = {k: v for k, v in row.items() if k in fields}
        common = {k: v for k, v in row.items() if k not in fields}
        identity_hash = row_hash(product_identity(row))
        product = await session.scalar(select(Product).where(Product.csv_row_hash == identity_hash))
        if product is None:
            candidates = list((await session.scalars(select(Product).where(
                Product.title == row["title"], Product.category == row["category"],
                Product.first_air_date == row["first_air_date"],
            ))).all())
            if len(candidates) > 1:
                raise ValueError(f"Ambiguous legacy product: {product_identity(row)}")
            product = candidates[0] if candidates else None
        counts["inserted" if product is None else "matched"] += 1
        if product is None:
            product = Product(**common, csv_row_hash=identity_hash)
            session.add(product)
        else:
            for key, value in common.items():
                setattr(product, key, value)
            product.csv_row_hash = identity_hash
        await session.flush()
        statement = insert(model).values(product_id=product.product_id, **detail)
        await session.execute(statement.on_conflict_do_update(index_elements=["product_id"], set_=detail))
    print(f"products: {dict(counts)}")


async def import_places(session, rows):
    counts = Counter()
    incoming = Counter((r["title"], r["name"], r["source"]) for r in rows)
    for row in rows:
        identity_hash = row_hash(place_identity(row))
        place = await session.scalar(select(Place).where(Place.csv_row_hash == identity_hash))
        if place is None:
            candidates = list((await session.scalars(select(Place).where(
                Place.title == row["title"], Place.name == row["name"], Place.source == row["source"],
            ).order_by(Place.place_id))).all())
            exact = [p for p in candidates if all(getattr(p, k) == row[k]
                     for k in ("address", "source_url", "latitude", "longitude"))]
            if exact:
                place = exact[0]  # Keep legacy duplicate IDs and references intact.
            elif len(candidates) == 1 and incoming[(row["title"], row["name"], row["source"])] == 1:
                place = candidates[0]
            elif candidates and incoming[(row["title"], row["name"], row["source"])] == 1:
                raise ValueError(f"Ambiguous changed place: {place_identity(row)}")
        if place is None:
            # Legacy KMDb places can have coordinates and an ID but no work title.
            # Reuse a uniquely identified row when curated CSV data supplies its title.
            legacy = list((await session.scalars(select(Place).where(
                Place.title.is_(None), Place.name == row["name"],
                Place.source == row["source"], Place.address == row["address"],
            ))).all())
            if len(legacy) == 1 and incoming[(row["title"], row["name"], row["source"])] == 1:
                place = legacy[0]
        counts["inserted" if place is None else "matched"] += 1
        if place is None:
            place = Place()
            session.add(place)
        location_changed = any(getattr(place, k) != row[k] for k in ("latitude", "longitude", "address"))
        for key, value in row.items():
            setattr(place, key, value)
        lat, lon = row["latitude"], row["longitude"]
        place.geom = WKTElement(f"POINT({lon} {lat})", srid=4326) if lat is not None and lon is not None else None
        place.csv_row_hash = identity_hash
        if location_changed:
            place.region_id = None
            place.tour_content_id = None
            place.tour_matched_at = None
        await session.flush()
    print(f"places: {dict(counts)}")


async def prune_missing_csv_rows(session, movies, dramas, places, only=None):
    """Remove CSV-managed rows absent from the current files, if no user data refers to them."""
    if only != "places":
        expected = {
            row_hash(product_identity(row)) for row in movies + dramas
        }
        managed = (await session.execute(
            select(Product.product_id, Product.csv_row_hash)
            .where(Product.csv_row_hash.is_not(None))
        )).all()
        product_ids = [row.product_id for row in managed if row.csv_row_hash not in expected]
        if product_ids:
            favorites = await session.scalar(
                select(func.count()).select_from(ProductFavorite)
                .where(ProductFavorite.product_id.in_(product_ids))
            )
            if favorites:
                raise ValueError(
                    f"Cannot prune {len(product_ids)} products: {favorites} product favorites exist"
                )
            await session.execute(delete(Product).where(Product.product_id.in_(product_ids)))
        print(f"Pruned CSV-managed products: {len(product_ids)}")

    if only != "products":
        expected = {row_hash(place_identity(row)) for row in places}
        managed = (await session.execute(
            select(Place.place_id, Place.csv_row_hash)
            .where(Place.csv_row_hash.is_not(None))
        )).all()
        place_ids = [row.place_id for row in managed if row.csv_row_hash not in expected]
        if place_ids:
            favorites = await session.scalar(
                select(func.count()).select_from(PlaceFavorite)
                .where(PlaceFavorite.place_id.in_(place_ids))
            )
            course_stops = await session.scalar(
                select(func.count()).select_from(CoursePlace)
                .where(CoursePlace.place_id.in_(place_ids))
            )
            if favorites or course_stops:
                raise ValueError(
                    f"Cannot prune {len(place_ids)} places: "
                    f"{favorites} favorites and {course_stops} course stops exist"
                )
            await session.execute(delete(Place).where(Place.place_id.in_(place_ids)))
        print(f"Pruned CSV-managed places: {len(place_ids)}")


async def seed(dry_run=False, only=None, prune=False):
    movies = load_rows("products_movie.csv", MOVIE_COLUMNS) if only != "places" else []
    dramas = load_rows("products_drama.csv", DRAMA_COLUMNS) if only != "places" else []
    places = load_rows("places.csv", PLACE_COLUMNS) if only != "products" else []
    print(f"Validated unique rows: movies={len(movies)}, dramas={len(dramas)}, places={len(places)}")
    if dry_run:
        return
    try:
        async with AsyncSessionLocal.begin() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(731942810)"))
            await import_products(session, movies)
            await import_products(session, dramas)
            await import_places(session, places)
            if prune:
                await prune_missing_csv_rows(session, movies, dramas, places, only)
        print("Commit complete" + ("" if prune else " (no rows deleted)"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=("products", "places"))
    parser.add_argument(
        "--prune", action="store_true",
        help="Delete CSV-managed rows absent from the current CSVs, unless user data refers to them.",
    )
    args = parser.parse_args()
    if args.dry_run and args.prune:
        parser.error("--dry-run validates CSVs only; run --prune separately")
    asyncio.run(seed(args.dry_run, args.only, args.prune))
