"""인증 입력·JWT·refresh 회전 잠금의 회귀 테스트."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.features.auth.schema import (
    GoogleLoginRequest,
    KakaoLoginRequest,
    LoginRequest,
    RefreshRequest,
)
from app.features.auth.service import rotate_tokens


class DeviceIdValidationTests(unittest.TestCase):
    def test_valid_device_id_is_accepted_by_all_auth_requests(self):
        device_id = "android_550e8400-e29b-41d4-a716-446655440000"

        self.assertEqual(
            LoginRequest(email="user@example.com", password="pw", device_id=device_id).device_id,
            device_id,
        )
        self.assertEqual(GoogleLoginRequest(id_token="token", device_id=device_id).device_id, device_id)
        self.assertEqual(KakaoLoginRequest(access_token="token", device_id=device_id).device_id, device_id)
        self.assertEqual(RefreshRequest(refresh_token="token", device_id=device_id).device_id, device_id)

    def test_whitespace_and_unsupported_characters_are_rejected(self):
        for device_id in ("        ", "device id", "device/id", "short"):
            with self.subTest(device_id=device_id), self.assertRaises(ValidationError):
                RefreshRequest(refresh_token="token", device_id=device_id)

    def test_device_id_longer_than_128_is_rejected(self):
        with self.assertRaises(ValidationError):
            RefreshRequest(refresh_token="token", device_id="a" * 129)


class AccessTokenTests(unittest.TestCase):
    def _encode(self, **overrides: object) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "7",
            "typ": "access",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            **overrides,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def test_access_token_contains_and_validates_issuer_and_audience(self):
        token = create_access_token(7)
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )

        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["iss"], settings.JWT_ISSUER)
        self.assertEqual(payload["aud"], settings.JWT_AUDIENCE)
        self.assertEqual(decode_access_token(token), 7)

    def test_wrong_issuer_or_audience_is_rejected(self):
        self.assertIsNone(decode_access_token(self._encode(iss="someone-else")))
        self.assertIsNone(decode_access_token(self._encode(aud="another-api")))


class _MissingTokenDb:
    def __init__(self):
        self.statement = None

    async def scalar(self, statement):
        self.statement = statement
        return None


class RefreshLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_lookup_requests_a_row_lock(self):
        db = _MissingTokenDb()

        with self.assertRaises(HTTPException) as raised:
            await rotate_tokens(db, "missing-token", "android_device-1234")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIsNotNone(db.statement._for_update_arg)


if __name__ == "__main__":
    unittest.main()
