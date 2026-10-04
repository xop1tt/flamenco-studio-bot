"""Контракт отображения времени: бот показывает время в поясе студии.

Те же контрольные точки проверяет сайт (FLAMENCO WEBSITE,
tests/format.test.mjs): один и тот же момент из PostgreSQL (UTC) должен
выглядеть одинаково в Telegram и в браузере.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from flamenco_bot.config import Config, parse_studio_timezone
from flamenco_bot.database.repository import ClassBooking
from flamenco_bot.presentation import cancellation_hint, format_class_time
from flamenco_bot.services import BookingService, NotificationReport
from flamenco_bot.studio_time import (
    format_studio_datetime,
    parse_studio_datetime,
    to_studio_time,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)

# (момент в UTC, как его показывают бот и сайт в Europe/Moscow)
CONTRACT = [
    (datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc), "Чт 08.10 · 19:00"),
    # Переход через полночь: в UTC ещё четверг, у студии уже пятница.
    (datetime(2026, 10, 8, 22, 30, tzinfo=timezone.utc), "Пт 09.10 · 01:30"),
    # Переход через год: дата студии уже в следующем году — год показывается.
    (datetime(2026, 12, 31, 21, 30, tzinfo=timezone.utc), "Пт 01.01.2027 · 00:30"),
]


class StudioTimezoneContractTests(unittest.TestCase):
    def test_default_studio_timezone_is_moscow(self):
        self.assertEqual(str(Config.STUDIO_TIMEZONE), "Europe/Moscow")

    def test_class_time_is_shown_in_studio_timezone(self):
        for moment, expected in CONTRACT:
            with self.subTest(moment=moment.isoformat()):
                self.assertEqual(format_class_time(moment, now=NOW), expected)

    def test_cancellation_deadline_is_shown_in_studio_timezone(self):
        starts_at = datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(
            cancellation_hint(starts_at, now=NOW),
            "Отменить запись можно до Ср 07.10 · 19:00.",
        )

    def test_admin_datetime_uses_studio_timezone_name(self):
        moment = datetime(2026, 10, 8, 22, 30, tzinfo=timezone.utc)
        self.assertEqual(format_studio_datetime(moment), "09.10.2026 01:30 MSK")

    def test_admin_input_without_offset_is_studio_time(self):
        moment = parse_studio_datetime("2026-10-08 19:00", "%Y-%m-%d %H:%M")
        self.assertEqual(
            moment.astimezone(timezone.utc),
            datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc),
        )

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            to_studio_time(datetime(2026, 10, 8, 16, 0))

    def test_timezone_rules_come_from_zoneinfo_not_fixed_offset(self):
        """Летнее/зимнее время — из правил пояса (проверяем на Europe/Berlin)."""
        with patch.object(Config, "STUDIO_TIMEZONE", ZoneInfo("Europe/Berlin")):
            summer = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
            winter = datetime(2026, 1, 15, 16, 0, tzinfo=timezone.utc)
            self.assertEqual(format_class_time(summer, now=NOW), "Ср 01.07 · 18:00")
            self.assertEqual(format_class_time(winter, now=NOW), "Чт 15.01 · 17:00")

    def test_invalid_timezone_is_rejected_and_empty_means_default(self):
        with self.assertRaises(ValueError):
            parse_studio_timezone("Mars/Olympus")
        self.assertEqual(str(parse_studio_timezone("")), "Europe/Moscow")


class AdminBookingNotificationTimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_notification_shows_studio_time(self):
        notifier = AsyncMock()
        notifier.notify.return_value = NotificationReport(recipients=1, delivered=1)
        service = BookingService(AsyncMock(), notifier)
        booking = ClassBooking(
            id=7,
            slot_id=3,
            telegram_id=1001,
            starts_at=datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc),
            class_key="beginner",
        )

        await service.notify_admins_about_booking(booking, "Анна")

        text = notifier.notify.await_args.args[0]
        self.assertIn("08.10.2026 19:00 MSK", text)
        self.assertNotIn("16:00", text)


if __name__ == "__main__":
    unittest.main()
