import hashlib
import hmac
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from flamenco_bot.api.app import create_app
from flamenco_bot.database import InMemoryRepository
from flamenco_bot.runtime.security import SupportRateLimiter
from flamenco_bot.services import AuthService


BOT_TOKEN = "123456:test-token"
SESSION_SECRET_KEY = "test-session-secret-at-least-32-bytes-long"


def sign_telegram_payload(payload, bot_token=BOT_TOKEN):
    data = dict(payload)
    check_string = "\n".join("{}={}".format(key, data[key]) for key in sorted(data))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    data["hash"] = hmac.new(
        secret_key, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return data


def make_telegram_payload(telegram_id=555, first_name="Анна", auth_date=None):
    return {
        "id": telegram_id,
        "first_name": first_name,
        "auth_date": int(auth_date if auth_date is not None else time.time()),
    }


class ClientAreaApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepository()
        app = create_app()
        app.state.repository = self.repository
        app.state.auth_service = AuthService(self.repository, BOT_TOKEN)
        app.state.session_secret_key = SESSION_SECRET_KEY
        app.state.bot = AsyncMock()
        app.state.support_limiter = SupportRateLimiter()
        self.client = TestClient(app, base_url="https://testserver")

    def _login_with_telegram(self, telegram_id=555):
        response = self.client.post(
            "/api/auth/telegram",
            json=sign_telegram_payload(make_telegram_payload(telegram_id=telegram_id)),
        )
        self.assertEqual(response.status_code, 200)

    def _register_email_only(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": "anna@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Анна",
            },
        )
        self.assertEqual(response.status_code, 201)

    async def _create_open_slot(self, class_key="beginner", capacity=1):
        return await self.repository.create_class_slot(
            class_key,
            datetime.now(timezone.utc) + timedelta(days=1),
            capacity,
            admin_telegram_id=1,
        )

    def test_schedule_is_public_and_lists_upcoming_slots(self):
        import asyncio

        slot = asyncio.run(self._create_open_slot())
        response = self.client.get("/api/schedule")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], slot.id)
        self.assertEqual(body[0]["remaining"], 1)

    def test_schedule_rejects_unknown_class_key(self):
        response = self.client.get("/api/schedule", params={"class_key": "nope"})
        self.assertEqual(response.status_code, 422)

    def test_packages_lists_catalog_without_auth(self):
        response = self.client.get("/api/packages")
        self.assertEqual(response.status_code, 200)
        keys = {package["key"] for package in response.json()}
        self.assertIn("single", keys)

    def test_booking_requires_login(self):
        response = self.client.post("/api/bookings", json={"slot_id": 1})
        self.assertEqual(response.status_code, 401)

    def test_booking_requires_linked_telegram(self):
        self._register_email_only()
        response = self.client.post("/api/bookings", json={"slot_id": 1})
        self.assertEqual(response.status_code, 409)

    def test_booking_confirms_slot_and_lists_it_under_me(self):
        import asyncio

        slot = asyncio.run(self._create_open_slot())
        self._login_with_telegram(telegram_id=777)

        response = self.client.post("/api/bookings", json={"slot_id": slot.id})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["slot_id"], slot.id)
        self.assertFalse(body["already_booked"])

        mine = self.client.get("/api/bookings/me")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(len(mine.json()), 1)
        self.assertEqual(mine.json()[0]["slot_id"], slot.id)

    def test_booking_rejects_full_slot(self):
        import asyncio

        slot = asyncio.run(self._create_open_slot(capacity=1))
        self._login_with_telegram(telegram_id=111)
        self.client.post("/api/bookings", json={"slot_id": slot.id})
        self.client.post("/api/auth/logout")

        self._login_with_telegram(telegram_id=222)
        response = self.client.post("/api/bookings", json={"slot_id": slot.id})
        self.assertEqual(response.status_code, 409)

    def test_support_requires_linked_telegram(self):
        self._register_email_only()
        response = self.client.post("/api/support", json={"body": "Вопрос"})
        self.assertEqual(response.status_code, 409)

    def test_support_submission_is_listed_under_me(self):
        self._login_with_telegram(telegram_id=999)
        response = self.client.post("/api/support", json={"body": "Не могу записаться"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["created"])

        mine = self.client.get("/api/support/me")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(len(mine.json()), 1)
        self.assertEqual(mine.json()[0]["last_message"], "Не могу записаться")

    def test_support_rejects_empty_message(self):
        self._login_with_telegram(telegram_id=888)
        response = self.client.post("/api/support", json={"body": "   "})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
