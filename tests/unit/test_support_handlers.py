import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from flamenco_bot.database.repository import ClassBooking, SlotUnavailableError
from flamenco_bot.handlers.support import (
    reply_to_support_ticket,
    submit_support_message,
)
from flamenco_bot.keyboards.user.lessons import book_class_slot
from flamenco_bot.runtime.security import SupportRateLimiter
from tests.support import FakeMessage, FakeRepository, FakeState


class SupportHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = FakeMessage(text="Вопрос о расписании")
        self.repository = FakeRepository()
        self.state = FakeState()
        self.limiter = SupportRateLimiter(max_messages=1)
        self.message.bot = SimpleNamespace(send_message=AsyncMock())

    async def test_support_message_is_stored_and_admins_are_notified(self):
        self.repository.list_admin_ids.return_value = [77]

        await submit_support_message(
            self.message,
            self.state,
            self.repository,
            self.limiter,
        )

        self.repository.create_support_message.assert_awaited_once_with(
            1001,
            "Вопрос о расписании",
        )
        self.message.bot.send_message.assert_awaited_once()
        self.assertEqual(self.message.bot.send_message.await_args.args[0], 77)
        self.assertIn(
            "Вопрос о расписании",
            self.message.bot.send_message.await_args.args[1],
        )
        self.assertIn("№1", self.message.last_answer.args[0])
        self.state.clear.assert_awaited_once()

    async def test_support_rate_limit_stops_repeated_messages(self):
        await submit_support_message(
            self.message,
            self.state,
            self.repository,
            self.limiter,
        )
        self.message.answer.reset_mock()
        self.message.text = "Ещё одно сообщение"

        await submit_support_message(
            self.message,
            self.state,
            self.repository,
            self.limiter,
        )

        self.repository.create_support_message.assert_awaited_once()
        self.assertIn("Слишком много сообщений", self.message.last_answer.args[0])

    async def test_oversized_support_message_is_rejected_before_storage(self):
        self.message.text = "x" * 2001

        await submit_support_message(
            self.message,
            self.state,
            self.repository,
            self.limiter,
        )

        self.repository.create_support_message.assert_not_awaited()
        self.assertIn("2000 символов", self.message.last_answer.args[0])

    async def test_admin_reply_is_authorized_and_delivered(self):
        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_profile.return_value = self.repository.profile
        self.message.text = "/support_reply 7 Ответ"

        await reply_to_support_ticket(self.message, self.repository)

        self.repository.reply_support_ticket.assert_awaited_once_with(7, 1001, "Ответ")
        self.message.bot.send_message.assert_awaited_once_with(
            1001,
            "Ответ службы поддержки по обращению №7:\nОтвет",
        )
        self.assertIn("доставлен", self.message.last_answer.args[0])

    async def test_non_admin_cannot_reply_to_support_ticket(self):
        self.message.text = "/support_reply 7 Ответ"

        await reply_to_support_ticket(self.message, self.repository)

        self.repository.reply_support_ticket.assert_not_awaited()
        self.assertIn("только администратору", self.message.last_answer.args[0])


class ClassBookingHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = FakeRepository()
        self.sender = SimpleNamespace(
            id=1001,
            full_name="Анна",
        )
        self.callback = SimpleNamespace(
            data="book:beginner:5",
            from_user=self.sender,
            answer=AsyncMock(),
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

    async def test_successful_callback_confirms_booking_and_notifies_user(self):
        starts_at = datetime.now(timezone.utc) + timedelta(days=1)
        self.repository.list_admin_ids.return_value = [77]
        self.repository.book_class_slot.return_value = ClassBooking(
            id=12,
            slot_id=5,
            telegram_id=1001,
            starts_at=starts_at,
            class_key="beginner",
        )

        await book_class_slot(self.callback, self.repository)

        self.repository.book_class_slot.assert_awaited_once_with(5, 1001)
        self.callback.answer.assert_awaited_once_with("Место подтверждено!")
        self.assertEqual(self.callback.bot.send_message.await_count, 2)
        self.assertIn(
            "Фламенко для начинающих",
            self.callback.bot.send_message.await_args_list[0].args[1],
        )
        self.assertEqual(
            self.callback.bot.send_message.await_args_list[1].args[0],
            77,
        )
        self.assertIn(
            "Новая запись",
            self.callback.bot.send_message.await_args_list[1].args[1],
        )

    async def test_callback_reports_slot_taken_without_success_message(self):
        self.repository.book_class_slot.side_effect = SlotUnavailableError("full")

        await book_class_slot(self.callback, self.repository)

        self.callback.answer.assert_awaited_once()
        self.assertTrue(self.callback.answer.await_args.kwargs["show_alert"])
        self.callback.bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
