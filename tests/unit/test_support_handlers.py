import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from flamenco_bot.database.repository import (
    BookingCooldownError,
    BookingNotFoundError,
    CancellationWindowExpiredError,
    ClassBooking,
    InsufficientLessonCreditsError,
    SlotUnavailableError,
    UserBooking,
)
from flamenco_bot.handlers.support import (
    reply_to_support_ticket,
    submit_support_message,
)
from flamenco_bot.keyboards.user.lessons import (
    book_class_slot,
    cancel_booking_callback,
    show_my_bookings,
)
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

    async def test_callback_reports_insufficient_credits_without_crashing(self):
        self.repository.book_class_slot.side_effect = InsufficientLessonCreditsError(
            "На балансе нет доступных занятий."
        )

        await book_class_slot(self.callback, self.repository)

        self.callback.answer.assert_awaited_once()
        self.assertTrue(self.callback.answer.await_args.kwargs["show_alert"])
        self.assertIn("абонемент", self.callback.answer.await_args.args[0])
        self.callback.bot.send_message.assert_not_awaited()

    async def test_callback_reports_rebooking_cooldown_without_crashing(self):
        self.repository.book_class_slot.side_effect = BookingCooldownError(
            "Повторная запись на это занятие после отмены будет доступна через 5 ч."
        )

        await book_class_slot(self.callback, self.repository)

        self.callback.answer.assert_awaited_once_with(
            "Повторная запись на это занятие после отмены будет доступна через 5 ч.",
            show_alert=True,
        )
        self.callback.bot.send_message.assert_not_awaited()


class MyBookingsHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = FakeRepository()
        self.message = FakeMessage()
        self.sender = SimpleNamespace(id=1001, full_name="Анна")
        self.callback = SimpleNamespace(
            data="cancel_booking:5",
            from_user=self.sender,
            answer=AsyncMock(),
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

    async def test_shows_only_upcoming_confirmed_bookings_with_cancel_buttons(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        self.repository.list_bookings_for_telegram_id.return_value = [
            UserBooking(
                id=1,
                slot_id=5,
                class_key="beginner",
                starts_at=future,
                booking_status="confirmed",
                slot_status="open",
            ),
            UserBooking(
                id=2,
                slot_id=6,
                class_key="individual",
                starts_at=past,
                booking_status="confirmed",
                slot_status="open",
            ),
            UserBooking(
                id=3,
                slot_id=7,
                class_key="intermediate",
                starts_at=future,
                booking_status="cancelled",
                slot_status="open",
            ),
        ]

        await show_my_bookings(self.message, self.repository)

        text_message = self.message.answer.await_args_list[0]
        self.assertIn("Фламенко для начинающих", text_message.args[0])
        self.assertNotIn("Индивидуальное занятие", text_message.args[0])
        self.assertNotIn("Продолжающая группа", text_message.args[0])

        keyboard_message = self.message.answer.await_args_list[1]
        buttons = keyboard_message.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0][0].callback_data, "cancel_booking:5")

    async def test_no_upcoming_bookings_shows_a_plain_message(self):
        self.repository.list_bookings_for_telegram_id.return_value = []

        await show_my_bookings(self.message, self.repository)

        self.message.answer.assert_awaited_once()
        self.assertIn("нет предстоящих", self.message.last_answer.args[0])

    async def test_cancel_callback_confirms_and_refunds(self):
        self.repository.cancel_class_slot_booking.return_value = True

        await cancel_booking_callback(self.callback, self.repository)

        self.repository.cancel_class_slot_booking.assert_awaited_once_with(5, 1001)
        self.callback.answer.assert_awaited_once_with(
            "Запись отменена, занятие возвращено на баланс."
        )

    async def test_cancel_callback_is_idempotent_for_already_cancelled(self):
        self.repository.cancel_class_slot_booking.return_value = False

        await cancel_booking_callback(self.callback, self.repository)

        self.callback.answer.assert_awaited_once_with("Запись уже была отменена ранее.")

    async def test_cancel_callback_reports_missing_booking(self):
        self.repository.cancel_class_slot_booking.side_effect = BookingNotFoundError(
            "Запись не найдена"
        )

        await cancel_booking_callback(self.callback, self.repository)

        self.callback.answer.assert_awaited_once_with(
            "Запись не найдена.", show_alert=True
        )

    async def test_cancel_callback_reports_expired_deadline(self):
        self.repository.cancel_class_slot_booking.side_effect = (
            CancellationWindowExpiredError(
                "Отмена доступна не позднее чем за 24 часа до начала занятия"
            )
        )

        await cancel_booking_callback(self.callback, self.repository)

        self.callback.answer.assert_awaited_once_with(
            "Отмена доступна не позднее чем за 24 часа до начала занятия",
            show_alert=True,
        )


if __name__ == "__main__":
    unittest.main()
