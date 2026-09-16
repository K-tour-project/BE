"""비밀번호 재설정의 검증, 1회 사용, 비밀번호 교체 동작."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.features.auth.schema import PasswordResetRequest
from app.features.auth.service import (
    _reset_code_hash,
    reset_password,
    send_password_reset_code,
    verify_password_reset_code,
)
from app.main import app
from app.models.auth import PasswordReset
from app.models.common import AuthProvider
from app.models.user import User


class PasswordResetContractTests(unittest.TestCase):
    def test_new_password_uses_signup_rules(self):
        PasswordResetRequest(reset_token="t" * 20, new_password="newpass123")
        for password in ("short1", "onlyletters", "한글" * 25 + "a1"):
            with self.subTest(password=password), self.assertRaises(ValidationError):
                PasswordResetRequest(reset_token="t" * 20, new_password=password)

    def test_reset_routes_are_public(self):
        paths = app.openapi()["paths"]
        for path in ("send-code", "verify-code", "confirm"):
            operation = paths[f"/auth/password-reset/{path}"]["post"]
            self.assertNotIn("security", operation)


class PasswordResetServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_row(self, code="123456"):
        return PasswordReset(
            reset_id=1,
            email="user@example.com",
            code_hash=_reset_code_hash("user@example.com", code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=3),
            attempt_count=0,
        )

    async def test_unknown_email_gets_generic_response_without_sending_mail(self):
        db = AsyncMock()
        db.scalar.return_value = None
        with patch("app.features.auth.service.mailer.send_verification_code", new_callable=AsyncMock) as send:
            result = await send_password_reset_code(db, "nobody@example.com")
        self.assertEqual(result, (settings.EMAIL_CODE_EXPIRE_MINUTES * 60, None))
        send.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_wrong_code_counts_attempt_and_correct_code_returns_one_time_token(self):
        row = self.make_row()
        db = AsyncMock()
        db.scalar.return_value = row
        with self.assertRaises(HTTPException) as error:
            await verify_password_reset_code(db, row.email, "000000")
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(row.attempt_count, 1)
        db.commit.assert_awaited_once()

        token = await verify_password_reset_code(db, row.email, "123456")
        self.assertGreaterEqual(len(token), 20)
        self.assertIsNotNone(row.reset_token_hash)
        self.assertIsNotNone(row.token_expires_at)
        with self.assertRaises(HTTPException):
            await verify_password_reset_code(db, row.email, "123456")

    async def test_reset_updates_password_and_revokes_sessions(self):
        row = self.make_row()
        row.reset_token_hash = "placeholder"
        row.token_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_VALID_MINUTES
        )
        user = User(
            user_id=7, nickname="Tester", auth_provider=AuthProvider.local,
            email=row.email, password_hash=hash_password("oldpass123"), email_verified=True,
        )
        db = AsyncMock()
        db.scalar.side_effect = [row, user]
        await reset_password(db, "reset-token", "newpass456")
        self.assertTrue(verify_password("newpass456", user.password_hash))
        self.assertFalse(verify_password("oldpass123", user.password_hash))
        self.assertEqual(db.execute.await_count, 2)
        db.commit.assert_awaited_once()
        self.assertIsNotNone(db.scalar.call_args_list[0].args[0]._for_update_arg)

        row.consumed_at = datetime.now(timezone.utc)
        db.scalar.side_effect = None
        db.scalar.return_value = row
        with self.assertRaises(HTTPException) as error:
            await reset_password(db, "reset-token", "another123")
        self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
