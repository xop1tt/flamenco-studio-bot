"""Сквозные сценарии через настоящий Dispatcher aiogram.

Юнит-тесты вызывают обработчики напрямую и не видят порядок роутеров и
FSM-фильтров — а именно он решает, куда попадёт сообщение пользователя.
Здесь апдейты проходят весь путь (роутеры, фильтры, FSM), а запросы к
Telegram перехватывает фейковая сессия.
"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from flamenco_bot.handlers import router
from flamenco_bot.handlers.states import LessonForm
from flamenco_bot.runtime.security import SupportRateLimiter
from tests.support import FakeRepository


USER_ID = 1001


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    async def make_request(self, bot, method, timeout=None):  # type: ignore[override]
        self.requests.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(
                message_id=len(self.requests),
                date=datetime.now(timezone.utc),
                chat=Chat(id=USER_ID, type="private"),
                text=method.text,
            )
        if isinstance(method, AnswerCallbackQuery):
            return True
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        return None


class BotRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = RecordingSession()
        self.bot = Bot(token="42:TEST", session=self.session)
        self.repository = FakeRepository()
        self.gateway = SimpleNamespace(
            is_configured=True,
            create_payment=AsyncMock(),
            get_payment=AsyncMock(),
        )
        self.dp = Dispatcher()
        self.dp["repository"] = self.repository
        self.dp["support_limiter"] = SupportRateLimiter()
        self.dp["payment_gateway"] = self.gateway
        self.dp["restart_controller"] = SimpleNamespace()
        self.dp.include_router(router)
        self.update_id = 0

    async def asyncTearDown(self):
        # Роутер модульный — отсоединяем, чтобы следующий тест мог
        # подключить его к новому Dispatcher.
        router._parent_router = None

    def user(self) -> User:
        return User(id=USER_ID, is_bot=False, first_name="Анна")

    async def send_text(self, text: str) -> None:
        self.update_id += 1
        message = Message(
            message_id=self.update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=USER_ID, type="private"),
            from_user=self.user(),
            text=text,
        )
        await self.dp.feed_update(
            self.bot, Update(update_id=self.update_id, message=message)
        )

    async def press(self, data: str) -> None:
        self.update_id += 1
        callback = CallbackQuery(
            id=str(self.update_id),
            from_user=self.user(),
            chat_instance="test",
            data=data,
            message=Message(
                message_id=500,
                date=datetime.now(timezone.utc),
                chat=Chat(id=USER_ID, type="private"),
                text="экран",
            ),
        )
        await self.dp.feed_update(
            self.bot, Update(update_id=self.update_id, callback_query=callback)
        )

    def last_text(self) -> str:
        for method in reversed(self.session.requests):
            if isinstance(method, (SendMessage, EditMessageText)):
                return method.text
        raise AssertionError("Бот ничего не ответил")

    async def state_of_user(self):
        key = StorageKey(bot_id=self.bot.id, chat_id=USER_ID, user_id=USER_ID)
        return await self.dp.storage.get_state(key)

    async def test_free_text_never_creates_payment(self):
        await self.send_text("💳 Покупки")
        await self.press("pack:single:0")
        for text in ("да", "нет", "Разовое занятие — 1000 ₽", "оплатить"):
            await self.send_text(text)

        self.repository.begin_lesson_payment_attempt.assert_not_awaited()
        self.gateway.create_payment.assert_not_awaited()
        self.assertIsNone(await self.state_of_user())

    async def test_old_purchase_session_is_reset_without_payment(self):
        key = StorageKey(bot_id=self.bot.id, chat_id=USER_ID, user_id=USER_ID)
        await self.dp.storage.set_state(
            key, LessonForm.waiting_for_purchase_confirmation
        )

        await self.send_text("привет")

        self.repository.begin_lesson_payment_attempt.assert_not_awaited()
        self.assertIsNone(await self.state_of_user())
        self.assertIn("кнопку «Оплатить»", self.last_text())

    async def test_menu_button_during_support_input_navigates_instead_of_ticket(self):
        await self.send_text("💬 Поддержка")
        self.assertEqual(await self.state_of_user(), "SupportForm:waiting_for_message")

        await self.send_text("💃 Мои занятия")

        self.repository.create_support_message.assert_not_awaited()
        self.assertIsNone(await self.state_of_user())
        self.assertIn("Мои занятия", self.last_text())

    async def test_inline_navigation_ends_unfinished_text_input(self):
        await self.send_text("👤 Профиль")
        await self.send_text("✏️ Изменить имя")
        await self.press("slots:all")

        await self.send_text("Случайный текст")

        self.repository.update_user_name.assert_not_awaited()
        self.assertIn("Не понял сообщение", self.last_text())

    async def test_support_message_is_saved_while_input_is_fresh(self):
        await self.send_text("💬 Поддержка")
        await self.send_text("Можно прийти без формы?")

        self.repository.create_support_message.assert_awaited_once_with(
            USER_ID, "Можно прийти без формы?"
        )
        self.assertIsNone(await self.state_of_user())

    async def test_old_cancel_button_asks_for_confirmation(self):
        await self.press("cancel_booking:5")

        self.repository.cancel_class_slot_booking.assert_not_awaited()

    async def test_reply_button_under_support_answer_opens_input(self):
        await self.press("support_reply")
        self.assertEqual(await self.state_of_user(), "SupportForm:waiting_for_message")

        await self.send_text("И ещё вопрос")

        self.repository.create_support_message.assert_awaited_once_with(
            USER_ID, "И ещё вопрос"
        )

    async def test_legacy_reply_buttons_reach_new_sections(self):
        await self.send_text("💃 Запись на занятия")
        self.assertIn("Ближайшие занятия", self.last_text())

        await self.send_text("🆘 Обратиться в поддержку")
        self.assertEqual(await self.state_of_user(), "SupportForm:waiting_for_message")


if __name__ == "__main__":
    unittest.main()
