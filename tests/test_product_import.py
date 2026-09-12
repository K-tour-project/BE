import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.models import DramaDetail, MovieDetail, Product
from scripts import seed_places_products as seed


class CsvTests(unittest.TestCase):
    def load(self, rows, movie=True):
        columns = seed.MOVIE_COLUMNS if movie else seed.DRAMA_COLUMNS
        filename = "products_movie.csv" if movie else "products_drama.csv"
        with tempfile.TemporaryDirectory() as directory:
            with (Path(directory) / filename).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            with patch.object(seed, "DATA", Path(directory)):
                return seed.load_rows(filename, columns)

    def test_movie_duplicate_and_null_normalization(self):
        row = dict(title="Example", category="MOVIE", genres="Drama, History")
        rows = self.load([row, row])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["genres"], "Drama|History")
        self.assertIsNone(rows[0]["runtime"])
        self.assertIsNone(rows[0]["first_air_date"])

    def test_conflicting_natural_key_duplicate_is_rejected(self):
        row = dict(title="Example", category="MOVIE", runtime="42")
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            self.load([row, dict(row, runtime="43")])

    def test_drama_mapping(self):
        row = {"제목": "작품", "카테고리": "DRAMA", "최초방영일": "2020-01-02",
               "장르": "드라마|역사", "주연배우": "배우1|배우2", "줄거리_번역여부": "FALSE",
               "에피소드수": "12", "작품유형": "Scripted"}
        result = self.load([row], movie=False)[0]
        self.assertEqual(result["first_air_date"], date(2020, 1, 2))
        self.assertFalse(result["overview_translated"])
        self.assertEqual(result["cast"], "배우1|배우2")
        self.assertEqual(result["episode_count"], 12)

    def test_identity_does_not_change_with_rating(self):
        row = dict(category="DRAMA", title="Example", first_air_date=None, rating=1)
        self.assertEqual(seed.row_hash(seed.product_identity(row)),
                         seed.row_hash(seed.product_identity(dict(row, rating=9))))

    def test_invalid_values_fail_before_database_write(self):
        for field, value in (("category", "DRAMA"), ("vote_average", "NaN"),
                             ("runtime", "-1"), ("release_date", "invalid")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load([dict(dict(title="Example", category="MOVIE"), **{field: value})])

    def test_shared_primary_keys_cascade_without_tmdb(self):
        for model in (MovieDetail, DramaDetail):
            self.assertEqual(list(model.__table__.primary_key.columns.keys()), ["product_id"])
            fk = next(iter(model.__table__.c.product_id.foreign_keys))
            self.assertEqual(fk.target_fullname, "products.product_id")
            self.assertEqual(fk.ondelete, "CASCADE")
            self.assertNotIn("tmdb_id", model.__table__.c)

    def test_places_optional_type_nulls_and_distinct_coordinates(self):
        rows = [{"제목": "작품", "장소명": "장소", "주소": "주소",
                 "위도": "37.12345678", "경도": "127", "데이터출처": "KMDb"}]
        rows += [dict(rows[0]), dict(rows[0], 위도="37.2")]
        with tempfile.TemporaryDirectory() as directory:
            with (Path(directory) / "places.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=seed.PLACE_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            with patch.object(seed, "DATA", Path(directory)):
                result = seed.load_rows("places.csv", seed.PLACE_COLUMNS)
        self.assertEqual(len(result), 2)
        self.assertEqual(str(result[0]["latitude"]), "37.1234568")
        self.assertNotIn("place_type", result[0])
        self.assertIsNone(result[0]["source_url"])


class ImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_movie_updates_existing_id_and_detail(self):
        product = Product(product_id=123, title="Example", category="MOVIE")
        session = AsyncMock()
        session.scalar.return_value = product
        row = dict(title="Example", category="MOVIE", first_air_date=None,
                   runtime=100, overview=None)
        await seed.import_products(session, [row])
        await seed.import_products(session, [dict(row, runtime=120)])
        session.add.assert_not_called()
        self.assertEqual(session.flush.await_count, 2)
        statement = session.execute.call_args.args[0]
        self.assertEqual(statement.compile().params["product_id"], 123)
        self.assertEqual(statement.compile().params["runtime"], 120)

    async def test_new_product_flushes_generated_id_before_detail_insert(self):
        session = AsyncMock()
        session.scalar.return_value = None
        session.scalars.return_value = Mock(all=Mock(return_value=[]))
        session.add = Mock()
        async def flush():
            session.add.call_args.args[0].product_id = 456
        session.flush.side_effect = flush
        await seed.import_products(session, [dict(title="New", category="MOVIE", first_air_date=None, runtime=90)])
        statement = session.execute.call_args.args[0]
        self.assertEqual(statement.compile().params["product_id"], 456)


if __name__ == "__main__":
    unittest.main()
