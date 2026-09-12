import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.features.home.service import (
    popular_products,
    popular_tourism_places,
)
from app.main import app
from app.models import Product


class HomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_popular_products_have_deterministic_rating_order_and_links(self):
        db = AsyncMock()
        db.scalars.return_value = Mock(all=Mock(return_value=[
            Product(
                product_id=7,
                title="작품",
                category="MOVIE",
                poster_url="poster",
                rating=9.2,
                popularity=100,
                first_air_date=date(2024, 5, 1),
            )
        ]))

        items = await popular_products(db)

        self.assertEqual(items[0].detail_path, "/contents/7")
        self.assertEqual(items[0].release_year, 2024)
        self.assertEqual(items[0].rating, 9.2)
        query = str(db.scalars.call_args.args[0])
        self.assertIn("products.rating DESC NULLS LAST", query)
        self.assertIn("products.popularity DESC NULLS LAST", query)
        self.assertIn("products.product_id ASC", query)
        self.assertIn("LIMIT", query)

    async def test_tourism_cards_keep_favorite_ranking_and_detail_path(self):
        ranked = SimpleNamespace(content_id="126508", favorite_count=5)
        db = AsyncMock()
        db.execute.return_value = Mock(all=Mock(return_value=[ranked]))
        api = AsyncMock()
        api.calls = []
        api.__aenter__.return_value = api
        api.__aexit__.return_value = None
        api.detail_common.return_value = {
            "title": "관광지",
            "firstimage": "image",
            "firstimage2": "thumb",
            "addr1": "서울특별시 종로구",
        }

        with (
            patch("app.features.home.service.TourApiClient", return_value=api),
            patch("app.features.home.service.save_calls", new=AsyncMock()) as save_calls,
        ):
            items = await popular_tourism_places(db, limit=1)

        self.assertEqual(items[0].favorite_count, 5)
        self.assertEqual(items[0].ranking_source, "FAVORITE_COUNT")
        self.assertEqual(items[0].detail_path, "/tourism-places/126508")
        self.assertEqual(items[0].sido_name, "서울특별시")
        api.detail_common.assert_awaited_once_with("126508")
        save_calls.assert_awaited_once_with(db, [])
        query = str(db.execute.call_args.args[0])
        self.assertIn("count(distinct(favorites.user_id))", query.lower())
        self.assertIn("coalesce(favorites.tour_content_id, places.tour_content_id)", query.lower())

    async def test_no_favorites_are_filled_with_inclusive_tour_api_cards(self):
        db = AsyncMock()
        db.execute.return_value = Mock(all=Mock(return_value=[]))
        api = AsyncMock()
        api.calls = []
        api.__aenter__.return_value = api
        api.__aexit__.return_value = None
        api.nationwide_recent_with_image.return_value = ([
            {"contentid": "1", "title": "무료 관광지", "firstimage": "one"},
            {"contentid": "2", "title": "유료 관광지", "firstimage": "two"},
        ], 2)
        with (
            patch("app.features.home.service.TourApiClient", return_value=api),
            patch("app.features.home.service.save_calls", new=AsyncMock()),
        ):
            items = await popular_tourism_places(db, limit=2)
        self.assertEqual([item.content_id for item in items], ["1", "2"])
        self.assertEqual({item.ranking_source for item in items}, {"TOUR_API_RECENT"})
        self.assertEqual([item.favorite_count for item in items], [0, 0])
        api.detail_common.assert_not_awaited()

    def test_home_route_is_publicly_registered(self):
        operation = app.openapi()["paths"]["/home"]["get"]
        self.assertEqual(operation["summary"], "홈 화면 인기 작품·관광지")
        self.assertNotIn("security", operation)

    def test_region_finder_routes_are_registered(self):
        paths = app.openapi()["paths"]
        self.assertIn("/regions/sidos", paths)
        self.assertIn("/regions/resolve", paths)
        self.assertIn("/regions/{sido_id}/children", paths)


if __name__ == "__main__":
    unittest.main()
