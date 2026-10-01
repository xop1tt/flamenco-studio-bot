import unittest
from datetime import datetime, timedelta, timezone

from flamenco_bot.database.repository import (
    InMemoryRepository,
    SlotUnavailableError,
)
from flamenco_bot.runtime.security import SupportRateLimiter


class SchedulingAndSupportTests(unittest.IsolatedAsyncioTestCase):
    async def test_class_booking_is_immediate_idempotent_and_capacity_limited(self):
        repository = InMemoryRepository()
        await repository.get_or_create_profile(1001, "Анна", False)
        await repository.get_or_create_profile(1002, "Мария", False)
        slot = await repository.create_class_slot(
            "beginner",
            datetime.now(timezone.utc) + timedelta(days=1),
            1,
            77,
        )

        first = await repository.book_class_slot(slot.id, 1001)
        repeated = await repository.book_class_slot(slot.id, 1001)
        self.assertFalse(first.already_booked)
        self.assertTrue(repeated.already_booked)
        self.assertEqual(first.id, repeated.id)
        self.assertEqual(
            (await repository.list_class_slots())[0].booked_count,
            1,
        )
        with self.assertRaises(SlotUnavailableError):
            await repository.book_class_slot(slot.id, 1002)

    async def test_slot_capacity_cannot_be_lowered_below_confirmed_bookings(self):
        repository = InMemoryRepository()
        await repository.get_or_create_profile(1001, "Анна", False)
        await repository.get_or_create_profile(1002, "Мария", False)
        slot = await repository.create_class_slot(
            "individual",
            datetime.now(timezone.utc) + timedelta(days=1),
            2,
            77,
        )
        await repository.book_class_slot(slot.id, 1001)
        await repository.book_class_slot(slot.id, 1002)

        with self.assertRaisesRegex(ValueError, "ниже числа"):
            await repository.update_class_slot_capacity(slot.id, 1)

        self.assertTrue(await repository.update_class_slot_capacity(slot.id, 2))
        self.assertTrue(await repository.close_class_slot(slot.id))
        with self.assertRaises(SlotUnavailableError):
            await repository.book_class_slot(slot.id, 1001)

    async def test_support_ticket_can_be_replied_to_closed_and_reopened(self):
        repository = InMemoryRepository()
        await repository.get_or_create_profile(1001, "Анна", False)

        ticket_id, created = await repository.create_support_message(1001, "Помогите")
        same_ticket_id, created_again = await repository.create_support_message(
            1001, "Дополнение"
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(ticket_id, same_ticket_id)
        self.assertEqual(
            (await repository.list_open_support_tickets())[0].last_message,
            "Дополнение",
        )
        self.assertEqual(
            await repository.reply_support_ticket(ticket_id, 77, "Проверяем"),
            1001,
        )
        self.assertEqual(
            (await repository.list_open_support_tickets())[0].last_message,
            "Проверяем",
        )
        self.assertEqual(await repository.close_support_ticket(ticket_id, 77), 1001)
        self.assertEqual(await repository.list_open_support_tickets(), [])
        reopened_id, reopened = await repository.create_support_message(
            1001, "Новый вопрос"
        )
        self.assertTrue(reopened)
        self.assertNotEqual(reopened_id, ticket_id)

    async def test_support_messages_are_validated(self):
        repository = InMemoryRepository()
        with self.assertRaisesRegex(ValueError, "1 до 2000"):
            await repository.create_support_message(1001, "  ")
        with self.assertRaisesRegex(ValueError, "1 до 2000"):
            await repository.create_support_message(1001, "x" * 2001)


class SupportRateLimiterTests(unittest.TestCase):
    def test_support_messages_are_limited_per_user_and_expire(self):
        current_time = [0.0]
        limiter = SupportRateLimiter(
            max_messages=2,
            window_seconds=10,
            max_tracked_users=2,
            clock=lambda: current_time[0],
        )
        self.assertTrue(limiter.allow(1))
        self.assertTrue(limiter.allow(1))
        self.assertFalse(limiter.allow(1))
        self.assertTrue(limiter.allow(2))
        self.assertTrue(limiter.allow(3))
        self.assertLessEqual(len(limiter._events), 2)

        current_time[0] = 11
        self.assertTrue(limiter.allow(1))
