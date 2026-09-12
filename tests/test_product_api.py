import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pydantic import TypeAdapter
from app.features.contents.schema import ProductDetail
from app.features.contents.service import (
    _filming_locations,
    _genre_set,
    _related_products,
    get_product,
)
from app.features.places.service import _contents_by_place
from app.models import Product, MovieDetail, DramaDetail


class ProductApiTests(unittest.IsolatedAsyncioTestCase):
    async def detail(self, product):
        db = AsyncMock()
        db.execute.side_effect = [
            Mock(first=Mock(return_value=(product, 3))),
            Mock(all=Mock(return_value=[])),
        ]
        db.scalar.return_value = 0
        db.scalars.return_value = Mock(all=Mock(return_value=[]))
        result = await get_product(db, product.product_id)
        return TypeAdapter(ProductDetail).dump_python(result)

    async def test_movie_only_returns_movie_fields(self):
        product = Product(product_id=1, title="Movie", category="MOVIE", networks="stale")
        product.movie_detail = MovieDetail(runtime=120)
        result = await self.detail(product)
        self.assertEqual(result["category"], "MOVIE")
        self.assertEqual(result["runtime"], 120)
        self.assertNotIn("networks", result)
        self.assertNotIn("tmdb_id", result)

    async def test_drama_reads_details_not_legacy_columns(self):
        product = Product(product_id=2, title="Drama", category="DRAMA", networks="stale")
        product.drama_detail = DramaDetail(networks="new", episode_count=16, cast="A|B", overview_translated=False)
        result = await self.detail(product)
        self.assertEqual(result["networks"], "new")
        self.assertEqual(result["episode_count"], 16)
        self.assertEqual(result["lead_actors"], "A|B")
        self.assertFalse(result["is_overview_translated"])
        self.assertNotIn("runtime", result)
        self.assertNotIn("tmdb_id", result)

    async def test_missing_optional_detail_returns_null_fields(self):
        product = Product(product_id=2, title="Drama", category="DRAMA", networks="stale")
        result = await self.detail(product)
        self.assertIsNone(result["networks"])

    async def test_missing_product(self):
        db = AsyncMock()
        db.execute.return_value = Mock(first=Mock(return_value=None))
        self.assertIsNone(await get_product(db, 999))

    async def test_related_products_are_ranked_by_rating(self):
        source = Product(product_id=1, title="Source", category="MOVIE", genres="코미디|드라마")
        exact = Product(product_id=2, title="Exact", category="DRAMA", genres="코미디|드라마", poster_url="a", rating=7.5)
        partial = Product(product_id=3, title="Partial", category="MOVIE", genres="코미디|액션", poster_url="b", rating=9.0)
        unrelated = Product(product_id=4, title="Other", category="MOVIE", genres="공포")
        db = AsyncMock()
        db.scalars.return_value = Mock(all=Mock(return_value=[partial, unrelated, exact]))

        result = await _related_products(db, source, 10)

        self.assertEqual([item.product_id for item in result], [3, 2])
        self.assertEqual(result[0].detail_path, "/contents/3")
        self.assertEqual(_genre_set(" 코미디|드라마|코미디 "), {"코미디", "드라마"})

    async def test_filming_locations_include_regions_and_place_link(self):
        db = AsyncMock()
        db.scalar.return_value = 1
        db.execute.return_value = Mock(all=Mock(return_value=[SimpleNamespace(
            place_id=7,
            tour_content_id="126508",
            name="촬영지",
            region_name="종로구",
            parent_name="서울특별시",
        )]))

        items, total = await _filming_locations(db, "작품", 20)

        self.assertEqual(total, 1)
        self.assertEqual(items[0].sido_name, "서울특별시")
        self.assertEqual(items[0].sigungu_name, "종로구")
        self.assertEqual(items[0].detail_path, "/places/7")

    async def test_place_uses_database_category_and_internal_id(self):
        db = AsyncMock()
        db.execute.side_effect = [
            Mock(all=Mock(return_value=[SimpleNamespace(place_id=10, name="Place")])),
            Mock(all=Mock(return_value=[SimpleNamespace(name="Place", product_id=42,
                title="Movie", category="MOVIE", poster_url="poster")]))]
        result = (await _contents_by_place(db, [10]))[10][0]
        self.assertEqual(result.category, "MOVIE")
        self.assertEqual(result.detail_path, "/contents/42")
        self.assertEqual(result.poster_url, "poster")
        self.assertIn("products.category", str(db.execute.call_args.args[0]))
