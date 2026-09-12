"""Opt-in PostgreSQL/ASGI tests; TEST_DATABASE_URL must name a separate test DB.

Migrate that database first. Every test rolls back its outer transaction, even
when an endpoint commits. TourAPI HTTP responses are stubbed, not sent live.
"""
import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.deps import get_db
from app.features.auth.social import SocialProfile
from app.features.auth.service import social_login
from app.integrations.tour_api import TourApiError
from app.main import app
from app.models import Place, PlaceFavorite, Product, ProductFavorite, Region, User, UserProfile
from app.models.auth import EmailVerification
from app.models.common import AuthProvider

TEST_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_URL, "Set TEST_DATABASE_URL to a separately migrated test database")
class MyPageDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_name = make_url(TEST_URL).database or ""
        if not database_name.startswith("ktour_mypage_test_"):
            raise RuntimeError("Use a dedicated ktour_mypage_test_* database")
        self.engine = create_async_engine(TEST_URL, poolclass=NullPool)
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self.db = AsyncSession(bind=self.connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        self.user = User(nickname="Tester", auth_provider=AuthProvider.google,
                         provider_user_id="mypage-test-1", email="one@example.com", email_verified=True)
        self.user.profile = UserProfile(profile_image_url="https://images.example.com/original.jpg")
        self.other = User(nickname="Other", auth_provider=AuthProvider.google,
                          provider_user_id="mypage-test-2", email="two@example.com", email_verified=True)
        boundary = func.ST_GeomFromText("MULTIPOLYGON(((126 37,127 37,127 38,126 38,126 37)))", 4326)
        sido = Region(name="서울특별시", level="1", bjd_cd="1100000000", boundary=boundary)
        self.db.add_all([self.user, self.other, sido])
        await self.db.flush()
        district = Region(name="종로구", level="2", bjd_cd="1111000000", parent_id=sido.region_id, boundary=boundary)
        self.db.add(district)
        await self.db.flush()
        self.place = Place(name="DB name", region_id=district.region_id, tour_content_id="126508")
        self.unmatched = Place(name="Unmatched")
        self.movie = Product(title="Movie", category="MOVIE", poster_url="https://images.example.com/movie.jpg",
                             first_air_date=date(2020, 4, 3))
        self.drama = Product(title="Drama", category="DRAMA")
        self.db.add_all([self.place, self.unmatched, self.movie, self.drama])
        await self.db.flush()

        async def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.headers = {"Authorization": f"Bearer {create_access_token(self.user.user_id)}"}
        self.other_headers = {"Authorization": f"Bearer {create_access_token(self.other.user_id)}"}
        self.api = AsyncMock()
        self.api.__aenter__.return_value = self.api
        self.api.calls = []
        self.api.detail_common.return_value = {
            "contentid": "126508", "title": "TourAPI name", "firstimage2": "https://images.example.com/thumb.jpg",
            "lDongRegnCd": "11", "lDongSignguCd": "110",
        }
        self.tour_patch = patch("app.features.mypage.service.TourApiClient", return_value=self.api)
        self.tour_patch.start()

    async def asyncTearDown(self):
        self.tour_patch.stop()
        app.dependency_overrides.clear()
        await self.client.aclose()
        await self.db.close()
        await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def request(self, method, path, **kwargs):
        kwargs.setdefault("headers", self.headers)
        response = await self.client.request(method, path, **kwargs)
        self.assertLess(response.status_code, 500, response.text)
        return response

    async def test_authentication_and_invalid_ids(self):
        response = await self.client.get("/me/mypage")
        self.assertEqual(response.status_code, 401)
        response = await self.request("PUT", "/me/favorites/places/0")
        self.assertEqual(response.status_code, 422)
        response = await self.request("PUT", "/me/favorites/tourism/not-a-number")
        self.assertEqual(response.status_code, 422)

    async def test_entry_returns_profile_counts_and_only_default_place_list(self):
        await self.request("PUT", f"/me/favorites/places/{self.place.place_id}")
        await self.request("PUT", f"/me/saved-products/{self.movie.product_id}")
        response = await self.request("GET", "/me/mypage")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user"], {"user_id": self.user.user_id, "nickname": "Tester",
                                       "email": "one@example.com", "profile_image_url": "https://images.example.com/original.jpg"})
        self.assertEqual(body["counts"], {"favorite_place_count": 1, "saved_product_count": 1})
        self.assertNotIn("saved_products", body)
        card = body["favorite_places"]["items"][0]
        self.assertEqual(card["name"], "TourAPI name")
        self.assertEqual(card["thumbnail_url"], "https://images.example.com/thumb.jpg")
        self.assertEqual((card["sido_name"], card["sigungu_name"]), ("서울특별시", "종로구"))
        self.assertEqual(card["detail_path"], f"/places/{self.place.place_id}")
        self.assertEqual(card["tour_status"], "ok")

    async def test_place_and_tourism_routes_share_one_favorite(self):
        first = (await self.request("PUT", f"/me/favorites/places/{self.place.place_id}")).json()
        again = (await self.request("PUT", "/me/favorites/tourism/126508")).json()
        self.assertEqual(first["favorite_id"], again["favorite_id"])
        self.assertEqual(again["favorite_place_count"], 1)
        self.api.detail_common.assert_not_awaited()
        response = (await self.request("DELETE", "/me/favorites/tourism/126508")).json()
        self.assertEqual(response["favorite_place_count"], 0)
        self.assertFalse(response["is_saved"])

    async def test_external_first_and_duplicate_filming_rows_do_not_duplicate(self):
        await self.request("PUT", "/me/favorites/tourism/126508")
        duplicate = Place(name="Another title", tour_content_id="126508")
        self.db.add(duplicate)
        await self.db.flush()
        response = await self.request("PUT", f"/me/favorites/places/{duplicate.place_id}")
        self.assertEqual(response.json()["favorite_place_count"], 1)

    async def test_preexisting_favorite_without_stored_tour_id_is_recognized(self):
        favorite = PlaceFavorite(user_id=self.user.user_id, place_id=self.place.place_id)
        self.db.add(favorite)
        await self.db.flush()
        response = await self.request("PUT", "/me/favorites/tourism/126508")
        self.assertEqual(response.json()["favorite_id"], favorite.favorite_id)
        self.assertEqual(response.json()["favorite_place_count"], 1)

    async def test_tourism_only_favorite_and_unmatched_place_have_correct_detail_paths(self):
        await self.request("PUT", "/me/favorites/tourism/999999")
        await self.request("PUT", f"/me/favorites/places/{self.unmatched.place_id}")
        cards = (await self.request("GET", "/me/favorite-places")).json()["items"]
        self.assertEqual(cards[0]["tour_status"], "unmatched")
        self.assertEqual(cards[0]["name"], "Unmatched")
        self.assertIsNone(cards[0]["thumbnail_url"])
        self.assertEqual(cards[1]["detail_path"], "/tourism-places/999999")
        self.assertIsNone(cards[1]["place_id"])

    async def test_other_user_cannot_read_or_cancel_saves(self):
        favorite = (await self.request("PUT", f"/me/favorites/places/{self.place.place_id}")).json()
        await self.request("PUT", f"/me/saved-products/{self.movie.product_id}")
        page = (await self.request("GET", "/me/mypage", headers=self.other_headers)).json()
        self.assertEqual(page["counts"], {"favorite_place_count": 0, "saved_product_count": 0})
        self.assertEqual(page["favorite_places"]["items"], [])
        await self.request("DELETE", f"/me/favorite-places/{favorite['favorite_id']}", headers=self.other_headers)
        await self.request("DELETE", f"/me/saved-products/{self.movie.product_id}", headers=self.other_headers)
        own = (await self.request("GET", "/me/mypage")).json()
        self.assertEqual(own["counts"], {"favorite_place_count": 1, "saved_product_count": 1})

    async def test_saved_products_are_paginated_and_have_year_and_category(self):
        await self.request("PUT", f"/me/saved-products/{self.movie.product_id}")
        await self.request("PUT", f"/me/saved-products/{self.movie.product_id}")
        await self.request("PUT", f"/me/saved-products/{self.drama.product_id}")
        page = (await self.request("GET", "/me/saved-products?limit=1&offset=1")).json()
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["items"][0]["release_year"], 2020)
        self.assertEqual(page["items"][0]["category"], "MOVIE")
        self.assertEqual(page["items"][0]["poster_url"], self.movie.poster_url)
        page = (await self.request("GET", "/me/saved-products?limit=1")).json()
        self.assertEqual(page["items"][0]["category"], "DRAMA")
        self.assertIsNone(page["items"][0]["release_year"])
        self.api.detail_common.assert_not_awaited()
        for _ in range(2):
            response = await self.request("DELETE", f"/me/saved-products/{self.movie.product_id}")
            self.assertEqual(response.json()["saved_product_count"], 1)

    async def test_favorite_pagination_and_idempotent_cancel(self):
        first = (await self.request("PUT", f"/me/favorites/places/{self.place.place_id}")).json()
        await self.request("PUT", f"/me/favorites/places/{self.unmatched.place_id}")
        page = (await self.request("GET", "/me/favorite-places?limit=1&offset=1")).json()
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["items"][0]["favorite_id"], first["favorite_id"])
        for _ in range(2):
            response = await self.request("DELETE", f"/me/favorite-places/{first['favorite_id']}")
            self.assertEqual(response.json()["favorite_place_count"], 1)
        page = (await self.request("GET", "/me/favorite-places?offset=10")).json()
        self.assertEqual(page, {"items": [], "total": 1})

    async def test_upstream_failure_keeps_place_count_and_db_fallback(self):
        await self.request("PUT", f"/me/favorites/places/{self.place.place_id}")
        self.api.detail_common.side_effect = TourApiError("offline")
        page = (await self.request("GET", "/me/mypage")).json()
        self.assertEqual(page["counts"]["favorite_place_count"], 1)
        self.assertEqual(page["favorite_places"]["items"][0]["tour_status"], "unavailable")
        self.assertEqual(page["favorite_places"]["items"][0]["name"], "DB name")

    async def test_missing_targets_do_not_create_saves(self):
        response = await self.request("PUT", "/me/saved-products/99999999")
        self.assertEqual(response.status_code, 404)
        response = await self.request("PUT", "/me/favorites/places/99999999")
        self.assertEqual(response.status_code, 404)
        self.api.detail_common.return_value = None
        response = await self.request("PUT", "/me/favorites/tourism/99999999")
        self.assertEqual(response.status_code, 404)
        counts = (await self.request("GET", "/me/mypage")).json()["counts"]
        self.assertEqual(counts, {"favorite_place_count": 0, "saved_product_count": 0})

    async def test_profile_update_reset_and_ownership(self):
        response = await self.request("PATCH", "/me/profile", json={"profile_image_url": "https://images.example.com/new.png"})
        self.assertEqual(response.json()["profile_image_url"], "https://images.example.com/new.png")
        me = (await self.request("GET", "/auth/me")).json()
        self.assertEqual(me["profile_image_url"], "https://images.example.com/new.png")
        other = (await self.request("GET", "/auth/me", headers=self.other_headers)).json()
        self.assertIsNone(other["profile_image_url"])
        response = await self.request("PATCH", "/me/profile", json={"profile_image_url": None})
        self.assertIsNone(response.json()["profile_image_url"])
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(UserProfile)), 0)

    async def test_signup_persists_submitted_profile(self):
        now = datetime.now(timezone.utc)
        self.db.add(EmailVerification(email="signup@example.com", code_hash="test-hash",
                                     expires_at=now, verified_at=now))
        await self.db.flush()
        response = await self.request("POST", "/auth/signup", json={
            "email": "signup@example.com", "password": "password123", "nickname": "New user",
            "profile_image_url": "https://images.example.com/signup.jpg",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user"]["profile_image_url"], "https://images.example.com/signup.jpg")

    async def test_existing_social_login_preserves_custom_profile(self):
        result = await social_login(self.db, SocialProfile(
            provider=AuthProvider.google, provider_user_id=self.user.provider_user_id,
            email=self.user.email, email_verified=True, nickname="Provider name",
            profile_image_url="https://images.example.com/provider.jpg",
        ), "test-device-1234")
        self.assertEqual(result.user.profile_image_url, "https://images.example.com/original.jpg")

    async def test_signup_without_picture_and_new_social_profile(self):
        now = datetime.now(timezone.utc)
        self.db.add(EmailVerification(email="without-image@example.com", code_hash="test-hash",
                                     expires_at=now, verified_at=now))
        await self.db.flush()
        response = await self.request("POST", "/auth/signup", json={
            "email": "without-image@example.com", "password": "password123", "nickname": "No image",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(response.json()["user"]["profile_image_url"])
        result = await social_login(self.db, SocialProfile(
            provider=AuthProvider.google, provider_user_id="new-google-account",
            email=None, email_verified=False, nickname="New social",
            profile_image_url="https://images.example.com/social.jpg",
        ), "test-device-1234")
        self.assertEqual(result.user.profile_image_url, "https://images.example.com/social.jpg")

    async def test_existing_product_detail_route_is_reachable(self):
        await self.request("PUT", f"/me/saved-products/{self.movie.product_id}")
        saved = (await self.request("GET", "/me/saved-products")).json()["items"][0]
        response = await self.request("GET", saved["detail_path"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["product_id"], self.movie.product_id)

    async def test_home_aggregates_tourism_favorites_and_returns_tour_detail_link(self):
        await self.request("PUT", f"/me/favorites/places/{self.place.place_id}")
        self.api.nationwide_recent_with_image.return_value = ([], 0)

        with patch("app.features.home.service.TourApiClient", return_value=self.api):
            response = await self.request("GET", "/home")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            body["tourism_ranking_basis"],
            "FAVORITE_COUNT_THEN_TOUR_API_RECENT",
        )
        self.assertEqual(len(body["popular_products"]), 2)
        self.assertEqual(body["popular_tourism_places"][0]["favorite_count"], 1)
        self.assertEqual(
            body["popular_tourism_places"][0]["detail_path"],
            "/tourism-places/126508",
        )
