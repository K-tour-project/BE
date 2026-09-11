import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.features.places.service import _related_tourism_places
from app.features.places.schema import TourDetail
from app.features.places.tourism import matches, list_tourism, tourism_detail
from app.integrations.tour_api import TourApiClient, intro_details


class TourismTests(unittest.IsolatedAsyncioTestCase):
    def test_place_detail_reports_image_count(self):
        detail = TourDetail(
            tour_content_id="123",
            images=["image-1", "image-2", "image-3"],
            image_count=3,
        )

        self.assertEqual(detail.image_count, len(detail.images))

    def test_same_name_requires_nearby_location(self):
        row = dict(contentid="123", title="같은 공원", mapy="37.5", mapx="127.0")
        place = SimpleNamespace(tour_content_id=None, name="같은공원", lat=37.5, lng=127.0, address=None)
        self.assertTrue(matches(row, place))
        place.lat = 35.0
        self.assertFalse(matches(row, place))
        # 저장된 TourAPI ID에는 의존하지 않고 매 요청 좌표와 이름으로 판정한다.
        place.tour_content_id = "123"
        self.assertFalse(matches(row, place))
        place.tour_content_id = "456"
        self.assertFalse(matches(row, place))

    def test_nearby_name_variation_is_filming_location(self):
        row = dict(contentid="123", title="리틀 포레스트 촬영지", mapy="36.1799", mapx="128.6647")
        place = SimpleNamespace(
            tour_content_id=None,
            name="영화 리틀포레스트 촬영지",
            lat=36.17991,
            lng=128.66469,
            address=None,
        )
        self.assertTrue(matches(row, place))

    def test_nearby_unrelated_name_is_not_filming_location(self):
        row = dict(contentid="123", title="다이소 서울역점", mapy="37.555", mapx="126.970")
        place = SimpleNamespace(
            tour_content_id=None,
            name="서울역",
            lat=37.5551,
            lng=126.9701,
            address=None,
        )
        self.assertFalse(matches(row, place))

    async def test_client_total_and_image_pagination(self):
        requests = []
        def handle(request):
            requests.append(request)
            page = request.url.params.get("pageNo")
            is_area = request.url.path.endswith("areaBasedList2")
            body = {"totalCount": 25 if is_area else 2, "items": {"item": {"contentid": "1"} if is_area else {"originimgurl": f"image{page}"}}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "0000"}, "body": body}})
        with patch("app.integrations.tour_api.settings") as settings:
            settings.tour_api_ready = True
            settings.TOUR_API_KEY = "test"
            settings.TOUR_API_TIMEOUT = 5
            settings.TOUR_API_APP_NAME = "test"
            settings.TOUR_API_BASE = "https://example.test"
            api = TourApiClient()
            await api.close()
            api._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
            async with api:
                rows, total = await api.area_based("11", "110")
                self.assertEqual(total, 25)
                self.assertEqual(len(rows), 1)
                self.assertEqual(requests[0].url.params["lDongSignguCd"], "110")
                self.assertEqual(len(await api.detail_images("1")), 2)
            self.assertNotIn("serviceKey", api.calls[0].params)

    async def test_keyword_search_only_includes_attractions_and_cultural_facilities(self):
        requests = []

        def handle(request):
            requests.append(request)
            content_type = request.url.params["contentTypeId"]
            item = {"contentid": content_type, "contenttypeid": content_type}
            body = {"totalCount": 1, "items": {"item": item}}
            return httpx.Response(200, json={"response": {"header": {"resultCode": "0000"}, "body": body}})

        with patch("app.integrations.tour_api.settings") as settings:
            settings.tour_api_ready = True
            settings.TOUR_API_KEY = "test"
            settings.TOUR_API_TIMEOUT = 5
            settings.TOUR_API_APP_NAME = "test"
            settings.TOUR_API_BASE = "https://example.test"
            api = TourApiClient()
            await api.close()
            api._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
            async with api:
                rows = await api.search_keyword("공원")

        self.assertEqual({row["contenttypeid"] for row in rows}, {"12", "14"})
        self.assertEqual(
            {request.url.params["contentTypeId"] for request in requests},
            {"12", "14"},
        )

    async def test_list_counts_names_and_classification(self):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(bjd_cd="1111000000", level="2")
        regions = [SimpleNamespace(bjd_cd="1100000000", name="서울특별시", level="1"), SimpleNamespace(bjd_cd="1111000000", name="종로구", level="2")]
        places = [SimpleNamespace(place_id=7, tour_content_id=None, name="공원", lat=37.5, lng=127, address=None)]
        db.execute.side_effect = [SimpleNamespace(all=lambda: regions), SimpleNamespace(all=lambda: places)]
        api = AsyncMock()
        api.__aenter__.return_value = api
        api.calls = []
        api.area_based.return_value = ([dict(contentid="123", title="공원", mapy="37.5", mapx="127", firstimage2="thumb")], 21)
        with patch("app.features.places.tourism.TourApiClient", return_value=api):
            result = await list_tourism(db, 1, 1, 20)
        self.assertEqual((result.total, result.count, result.has_next), (21, 1, True))
        self.assertEqual(result.items[0].category, "촬영지")
        self.assertEqual(result.items[0].sigungu_name, "종로구")
        self.assertEqual(result.items[0].place_ids, [7])

    async def test_detail_uses_content_id_and_original_images(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(all=lambda: [])
        api = AsyncMock()
        api.__aenter__.return_value = api
        api.calls = []
        api.detail_common.return_value = dict(title="공원", overview="소개<br>설명", homepage='<a href="https://example.test">홈페이지</a>', addr1="서울", tel="02-123", contenttypeid="12")
        api.detail_intro.return_value = dict(
            usetime="09:00~18:00", restdate="월요일", parking="가능", chkpet="불가"
        )
        api.detail_images.return_value = [{"originimgurl": "original"}, {"originimgurl": "original"}, {}]
        with patch("app.features.places.tourism.TourApiClient", return_value=api):
            result = await tourism_detail(db, "123")
        self.assertEqual(result.images, ["original"])
        self.assertEqual(result.homepage, "https://example.test")
        self.assertEqual(result.address, "서울")
        self.assertEqual(result.use_time, "09:00~18:00")
        self.assertEqual(result.parking, "가능")
        self.assertEqual(result.pet_allowed, "불가")
        api.detail_common.assert_awaited_once_with("123")

    def test_intro_details_supports_cultural_facilities(self):
        self.assertEqual(
            intro_details(
                {
                    "usetimeculture": "10:00~20:00",
                    "restdateculture": "화요일",
                    "parkingculture": "주차 가능",
                    "chkpetculture": "안내견 가능",
                },
                "14",
            ),
            ("10:00~20:00", "화요일", "주차 가능", "안내견 가능"),
        )

    async def test_related_places_are_resolved_to_clickable_content_ids(self):
        api = AsyncMock()
        api.related_spots.return_value = [
            {
                "tAtsNm": "현재 공원",
                "rlteTatsCd": f"related-{i}",
                "rlteTatsNm": f"연관 장소 {i}",
                "rlteRegnNm": "서울특별시",
                "rlteSignguNm": "종로구",
                "rlteRank": str(i),
            }
            for i in range(1, 8)
        ]
        api.search_keyword.side_effect = [
            [{"contentid": str(100 + i), "title": f"연관 장소 {i}"}]
            for i in range(1, 8)
        ]
        common = {"title": "현재 공원", "lDongRegnCd": "11", "lDongSignguCd": "11110"}
        row = SimpleNamespace(name="현재 공원", region_bjd_cd="1111000000")

        result = await _related_tourism_places(api, common, row)

        self.assertEqual(len(result), 6)
        self.assertEqual(result[0].content_id, "101")
        self.assertEqual(result[0].detail_path, "/tourism-places/101")
        self.assertEqual(result[0].sido_name, "서울특별시")


if __name__ == "__main__":
    unittest.main()
