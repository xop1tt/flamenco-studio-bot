import unittest
from typing import cast
from unittest.mock import AsyncMock

from aiogram.types import TelegramObject

from flamenco_bot.runtime.security import AuthRateLimiter, SecurityMiddleware
from tests.support import FakeMessage


class SecurityMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_messages_pass_within_rate_limit(self):
        middleware = SecurityMiddleware(max_events=2, window_seconds=5)
        handler = AsyncMock(return_value="handled")
        message = FakeMessage()

        event = cast(TelegramObject, message)
        self.assertEqual(await middleware(handler, event, {}), "handled")
        self.assertEqual(await middleware(handler, event, {}), "handled")
        handler.assert_awaited_with(message, {})

    async def test_excess_messages_are_dropped_and_warning_is_rate_limited(self):
        middleware = SecurityMiddleware(max_events=1, window_seconds=5)
        handler = AsyncMock()
        message = FakeMessage()

        with self.assertLogs("bot.security", level="WARNING") as logs:
            event = cast(TelegramObject, message)
            await middleware(handler, event, {})
            self.assertIsNone(await middleware(handler, event, {}))
            self.assertIsNone(await middleware(handler, event, {}))

        handler.assert_awaited_once()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("telegram_id=1001", logs.output[0])

    async def test_non_private_messages_are_dropped(self):
        middleware = SecurityMiddleware()
        handler = AsyncMock()
        message = FakeMessage()
        message.chat.type = "group"

        self.assertIsNone(await middleware(handler, cast(TelegramObject, message), {}))
        handler.assert_not_awaited()

    async def test_user_tracking_is_bounded_and_expired_entries_are_removed(self):
        current_time = [0.0]
        middleware = SecurityMiddleware(
            max_events=2,
            window_seconds=5,
            max_tracked_users=2,
            clock=lambda: current_time[0],
        )
        handler = AsyncMock()

        for user_id in (1, 2, 3):
            await middleware(
                handler,
                cast(TelegramObject, FakeMessage(telegram_id=user_id)),
                {},
            )
        self.assertEqual(len(middleware._events), 2)

        current_time[0] = 6.0
        await middleware(
            handler,
            cast(TelegramObject, FakeMessage(telegram_id=4)),
            {},
        )
        self.assertEqual(len(middleware._events), 1)
        self.assertIn(4, middleware._events)

    async def test_global_event_limit_drops_bursts(self):
        current_time = [0.0]
        middleware = SecurityMiddleware(
            max_global_events=2,
            global_window_seconds=1,
            clock=lambda: current_time[0],
        )
        handler = AsyncMock(return_value="handled")
        first = cast(TelegramObject, FakeMessage(telegram_id=1))
        second = cast(TelegramObject, FakeMessage(telegram_id=2))
        third = cast(TelegramObject, FakeMessage(telegram_id=3))

        self.assertEqual(await middleware(handler, first, {}), "handled")
        self.assertEqual(await middleware(handler, second, {}), "handled")
        self.assertIsNone(await middleware(handler, third, {}))
        current_time[0] = 1
        self.assertEqual(await middleware(handler, third, {}), "handled")

    def test_invalid_rate_limit_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            SecurityMiddleware(max_events=0)


class AuthRateLimiterTests(unittest.TestCase):
    def test_allows_up_to_the_configured_number_of_attempts(self):
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=5)

        self.assertTrue(limiter.allow("1.2.3.4"))
        self.assertTrue(limiter.allow("1.2.3.4"))
        self.assertFalse(limiter.allow("1.2.3.4"))

    def test_different_keys_have_independent_budgets(self):
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=5)

        self.assertTrue(limiter.allow("1.2.3.4"))
        self.assertFalse(limiter.allow("1.2.3.4"))
        self.assertTrue(limiter.allow("5.6.7.8"))

    def test_budget_resets_after_the_window_elapses(self):
        current_time = [0.0]
        limiter = AuthRateLimiter(
            max_attempts=1, window_seconds=5, clock=lambda: current_time[0]
        )

        self.assertTrue(limiter.allow("1.2.3.4"))
        self.assertFalse(limiter.allow("1.2.3.4"))
        current_time[0] = 5.1
        self.assertTrue(limiter.allow("1.2.3.4"))

    def test_tracked_keys_are_bounded(self):
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=5, max_tracked_keys=2)

        limiter.allow("1.1.1.1")
        limiter.allow("2.2.2.2")
        limiter.allow("3.3.3.3")

        self.assertEqual(len(limiter._events), 2)
        self.assertNotIn("1.1.1.1", limiter._events)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            AuthRateLimiter(max_attempts=0)
