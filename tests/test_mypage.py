"""My Page validation and external-service behavior without a database."""
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError

from app.features.auth.schema import SignupRequest
from app.features.auth.social import _profile_image_url
from app.features.mypage.schema import ProfileUpdate
from app.features.mypage.service import _live_places
from app.integrations.tour_api import TourApiError, TourApiKeyMissing
from app.main import app


class ProfileContractTests(unittest.TestCase):
    def test_signup_accepts_optional_image_url(self):
        request = SignupRequest(email="user@example.com", nickname="Tester", password="password123",
                                profile_image_url="https://images.example.com/a.jpg")
        self.assertEqual(str(request.profile_image_url), "https://images.example.com/a.jpg")

    def test_profile_update_requires_field_and_disallows_arbitrary_fields(self):
        for body in ({}, {"profile_image_url": "javascript:alert(1)"},
                     {"profile_image_url": "file:///etc/passwd"},
                     {"profile_image_url": "https://example.com/a.jpg", "user_id": 5}):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                ProfileUpdate.model_validate(body)
        self.assertIsNone(ProfileUpdate(profile_image_url=None).profile_image_url)

    def test_social_image_validation(self):
        self.assertEqual(_profile_image_url("https://example.com/a.jpg"), "https://example.com/a.jpg")
        self.assertIsNone(_profile_image_url("javascript:alert(1)"))
        self.assertIsNone(_profile_image_url(None))

    def test_application_registers_mypage_and_existing_detail_routes(self):
        paths = app.openapi()["paths"]
        for path in ("/me/mypage", "/me/favorite-places", "/me/saved-products", "/me/profile",
                     "/places/{place_id}", "/tourism-places/{content_id}", "/contents/{product_id}"):
            self.assertIn(path, paths)
        self.assertIn("security", paths["/me/mypage"]["get"])


class LiveFavoriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_page_does_not_create_tour_api_client(self):
        with patch("app.features.mypage.service.TourApiClient") as factory:
            self.assertEqual(await _live_places(AsyncMock(), 1, set()), {})
            factory.assert_not_called()

    async def test_one_upstream_failure_does_not_hide_other_saved_places(self):
        api = AsyncMock()
        api.__aenter__.return_value = api
        api.calls = [Mock()]

        async def detail(cid):
            if cid == "2":
                raise TourApiError("unavailable")
            return {"title": "Place"} if cid == "1" else None

        api.detail_common.side_effect = detail
        with patch("app.features.mypage.service.TourApiClient", return_value=api), \
             patch("app.features.mypage.service.save_calls", new_callable=AsyncMock) as logs:
            result = await _live_places(AsyncMock(), 7, {"1", "2", "3"})
        self.assertEqual([result[cid][1] for cid in ("1", "2", "3")], ["ok", "unavailable", "not_found"])
        logs.assert_awaited_once()
        self.assertEqual(logs.call_args.kwargs["user_id"], 7)

    async def test_missing_key_keeps_saved_rows_available(self):
        with patch("app.features.mypage.service.TourApiClient", side_effect=TourApiKeyMissing()):
            self.assertEqual(await _live_places(AsyncMock(), 1, {"1"}), {"1": (None, "unavailable")})
