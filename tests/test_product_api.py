import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pydantic import TypeAdapter
from app.features.contents.schema import ProductDetail
from app.features.contents.service import get_product
from app.features.places.service import _contents_by_place
from app.models import Product, MovieDetail, DramaDetail


class ProductApiTests(unittest.IsolatedAsyncioTestCase):
    async def detail(self, product):
        db = AsyncMock()
        db.execute.return_value = Mock(first=Mock(return_value=(product, 3)))
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
