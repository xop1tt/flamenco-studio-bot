from dataclasses import replace
from datetime import datetime, timedelta
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from flamenco_bot.handlers.admin import (
    cancel_bot_restart,
    cancel_scheduled_restart,
    confirm_bot_restart,
    open_bot_management_menu,
    request_bot_restart,
    save_restart_schedule,
    start_scheduling_restart,
    show_bot_status,
)
from flamenco_bot.handlers.states import AdminForm
from flamenco_bot.keyboards.admin import (
    BOT_MANAGEMENT_MENU,
    BOT_RESTART,
    BOT_RESTART_CANCEL,
    BOT_RESTART_CONFIRM,
    BOT_STATUS,
    BOT_SCHEDULE_RESTART,
    BOT_CANCEL_SCHEDULED_RESTART,
    bot_management_keyboard,
    bot_restart_confirmation_keyboard,
)
from flamenco_bot.keyboards.user import main_menu_keyboard
from tests.support import FakeMessage, FakeRepository, FakeState


class AdminManagementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = FakeMessage(telegram_id=1001)
        self.state = FakeState()
        self.repository = FakeRepository()
        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_profile.return_value = self.repository.profile
        self.controller = SimpleNamespace(
            started_at=time.monotonic() - 61,
            restart_reason=None,
            scheduled_restart_at=None,
            request_restart=AsyncMock(),
            schedule_restart=AsyncMock(),
            cancel_scheduled_restart=AsyncMock(return_value=True),
        )

    async def test_management_entry_is_admin_only_and_has_own_menu(self):
        await open_bot_management_menu(
            self.message,
            self.state,
            self.repository,
        )

        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            bot_management_keyboard(),
        )
        self.state.clear.assert_awaited_once()

        self.message.answer.reset_mock()
        self.message.from_user.id = 1002
        await open_bot_management_menu(
            self.message,
            self.state,
            self.repository,
        )

        self.assertIn("только администратору", self.message.last_answer.args[0])

    async def test_management_actions_show_status_and_require_confirmation(self):
        with patch(
            "flamenco_bot.handlers.admin.get_process_resources",
            return_value=(42.5, 3.25),
        ):
            await show_bot_status(self.message, self.controller, self.repository)
        self.assertIn("Бот работает", self.message.last_answer.args[0])
        self.assertIn("0 ч 1 мин", self.message.last_answer.args[0])
        self.assertIn("CPU с запуска: 3.2 сек", self.message.last_answer.args[0])
        self.assertIn("Пиковая память: 42.5 МБ", self.message.last_answer.args[0])
        self.assertIn("Пользователей всего: 10", self.message.last_answer.args[0])
        self.assertIn("Активны за 5 минут: 2", self.message.last_answer.args[0])
        self.repository.get_user_statistics.assert_awaited_once()

        self.message.text = BOT_MANAGEMENT_MENU
        await request_bot_restart(self.message, self.state, self.repository)
        self.assertEqual(
            self.state.current_state,
            AdminForm.waiting_for_restart_confirmation.state,
        )
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            bot_restart_confirmation_keyboard(),
        )

        self.message.text = BOT_RESTART_CONFIRM
        await confirm_bot_restart(
            self.message,
            self.state,
            self.controller,
            self.repository,
        )

        self.controller.request_restart.assert_awaited_once_with("admin_requested")
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            main_menu_keyboard(is_admin=True),
        )

    async def test_restart_cancel_clears_confirmation_state_without_restarting(self):
        await request_bot_restart(self.message, self.state, self.repository)
        self.message.text = BOT_RESTART_CANCEL
        await cancel_bot_restart(self.message, self.state, self.repository)

        self.assertIsNone(self.state.current_state)
        self.controller.request_restart.assert_not_awaited()
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            bot_management_keyboard(),
        )

    async def test_restart_can_be_scheduled_and_cancelled(self):
        self.message.text = BOT_SCHEDULE_RESTART
        await start_scheduling_restart(
            self.message,
            self.state,
            self.repository,
        )
        self.assertEqual(
            self.state.current_state,
            AdminForm.waiting_for_scheduled_restart.state,
        )

        scheduled_at = datetime.now().astimezone() + timedelta(hours=2)
        self.message.text = scheduled_at.strftime("%Y-%m-%d %H:%M")
        await save_restart_schedule(
            self.message,
            self.state,
            self.controller,
            self.repository,
        )
        self.controller.schedule_restart.assert_awaited_once()
        self.assertIn("Перезапуск запланирован", self.message.last_answer.args[0])

        self.message.text = BOT_CANCEL_SCHEDULED_RESTART
        await cancel_scheduled_restart(
            self.message,
            self.state,
            self.controller,
            self.repository,
        )
        self.controller.cancel_scheduled_restart.assert_awaited_once()
        self.assertIn("отменён", self.message.last_answer.args[0])

    async def test_admin_actions_are_rejected_outside_private_chat(self):
        self.message.chat.type = "group"
        await show_bot_status(self.message, self.controller, self.repository)

        self.assertIn("только администратору", self.message.last_answer.args[0])
        self.controller.request_restart.assert_not_awaited()

    async def test_keyboard_labels_expose_status_restart_and_cancel(self):
        management_labels = {
            button.text for row in bot_management_keyboard().keyboard for button in row
        }
        confirmation_labels = {
            button.text
            for row in bot_restart_confirmation_keyboard().keyboard
            for button in row
        }
        self.assertIn(BOT_STATUS, management_labels)
        self.assertIn(BOT_RESTART, management_labels)
        self.assertIn(BOT_RESTART_CONFIRM, confirmation_labels)
        self.assertIn(BOT_RESTART_CANCEL, confirmation_labels)
