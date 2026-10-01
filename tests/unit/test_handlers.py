import hashlib
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from aiogram.types import Message

from flamenco_bot.commands import get_bot_commands
from flamenco_bot.handlers.admin import (
    admin_command,
    complete_request,
    list_requests,
    save_participant_name,
    save_participant_phone,
    search_participants,
    select_name_target,
    select_phone_target,
    start_edit_participant_name,
    start_edit_participant_phone,
    start_participant_search,
)
from flamenco_bot.handlers.core import (
    account_command,
    buy_command,
    cancel_command,
    help_command,
    lessons_command,
    schedule_command,
    start_command,
)
from flamenco_bot.handlers.fallback import fallback_message
from flamenco_bot.keyboards.user.account import (
    open_account_menu,
    request_name,
    request_phone,
    return_from_account,
    save_name,
    save_phone,
    show_account,
    verify_phone_code,
)
from flamenco_bot.keyboards.user.lessons import (
    back_to_classes,
    back_to_purchase_menu,
    cancel_lesson_flow,
    check_lesson_payment,
    choose_class,
    return_from_lessons,
    select_class,
    select_purchase,
    submit_booking_request,
    submit_purchase_request,
)
from flamenco_bot.payments import ProviderPayment
from flamenco_bot.database.repository import LessonPayment
from flamenco_bot.keyboards.user.main_menu import (
    cancel_from_menu,
    back_to_lessons_menu,
    ensure_profile,
    open_account_from_menu,
    open_class_menu,
    open_lessons_from_menu,
    open_purchase_menu,
    show_main_menu,
    show_schedule,
    show_studio_info,
)
from flamenco_bot.keyboards.user import (
    account_menu_keyboard,
    class_menu_keyboard,
    lessons_menu_keyboard,
    main_menu_keyboard,
    phone_request_keyboard,
    purchase_menu_keyboard,
)
from flamenco_bot.handlers.states import AccountForm, LessonForm
from flamenco_bot.handlers.states import AdminForm
from tests.support import FakeMessage, FakeRepository, FakeState


class BotFunctionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = FakeMessage()
        self.repository = FakeRepository()
        self.state = FakeState()

    async def test_start_registers_and_shows_main_menu(self):
        await start_command(self.message, self.repository, self.state)
        self.repository.get_or_create_profile.assert_awaited_once_with(
            telegram_id=1001,
            user_name="Анна",
            is_admin=False,
        )
        self.state.clear.assert_awaited_once()
        self.assertIn("студию фламенко", self.message.last_answer.args[0])
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            main_menu_keyboard(),
        )

    async def test_start_shows_admin_panel_from_database_profile(self):
        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_or_create_profile.return_value = self.repository.profile

        await start_command(self.message, self.repository, self.state)

        buttons = {
            button.text
            for row in self.message.last_answer.kwargs["reply_markup"].keyboard
            for button in row
        }
        self.assertIn("🛠 Админ-меню", buttons)
        self.assertIn("⚙️ Управление ботом", buttons)

    async def test_help_mentions_user_and_admin_commands(self):
        await help_command(self.message, self.state, self.repository)
        text = self.message.last_answer.args[0]
        self.assertIn("/schedule", text)
        self.assertIn("/requests", text)
        self.state.clear.assert_awaited_once()

    async def test_account_command_loads_profile(self):
        await account_command(self.message, self.repository, self.state)
        self.repository.get_or_create_profile.assert_awaited_once()
        self.assertIn("Telegram ID: 1001", self.message.last_answer.args[0])

    async def test_lessons_command_shows_lessons_keyboard(self):
        await lessons_command(self.message, self.repository, self.state)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            lessons_menu_keyboard(),
        )

    async def test_schedule_does_not_claim_availability(self):
        await schedule_command(self.message, self.state)
        self.assertIn("подтвердил свободное время", self.message.last_answer.args[0])

    async def test_buy_explains_yookassa_checkout(self):
        await buy_command(self.message, self.repository, self.state)
        self.assertIn("ЮKassa", self.message.last_answer.args[0])
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            purchase_menu_keyboard(),
        )

    async def test_cancel_clears_fsm(self):
        await cancel_command(self.message, self.state, self.repository)
        self.state.clear.assert_awaited_once()

    async def test_cancel_returns_to_parent_menu_for_current_action(self):
        await self.state.set_state(AccountForm.waiting_for_phone_code)
        await cancel_command(self.message, self.state, self.repository)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            account_menu_keyboard(),
        )

        await self.state.set_state(LessonForm.waiting_for_purchase_confirmation)
        await cancel_command(self.message, self.state, self.repository)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            purchase_menu_keyboard(),
        )

        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_profile.return_value = self.repository.profile
        await self.state.set_state(AdminForm.waiting_for_search)
        await cancel_command(self.message, self.state, self.repository)
        self.assertIn(
            "🔎 Найти участника",
            {
                button.text
                for row in self.message.last_answer.kwargs["reply_markup"].keyboard
                for button in row
            },
        )

    async def test_ensure_profile_uses_telegram_identity(self):
        profile = await ensure_profile(
            cast(Message, self.message),
            self.repository,
        )
        self.assertEqual(profile.telegram_id, 1001)

    async def test_all_main_menu_actions_answer(self):
        await show_main_menu(self.message, self.state, self.repository)
        await open_account_from_menu(self.message, self.state)
        await open_lessons_from_menu(self.message, self.state)
        await show_schedule(self.message, self.state)
        await open_purchase_menu(self.message, self.state)
        await open_class_menu(self.message, self.state)
        await cancel_from_menu(self.message, self.state, self.repository)
        await show_studio_info(self.message, self.repository)
        self.assertEqual(self.message.answer.await_count, 8)
        self.repository.get_or_create_profile.assert_not_awaited()

    async def test_account_display_includes_required_fields(self):
        await open_account_menu(self.message, self.state)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            account_menu_keyboard(),
        )
        self.assertIn("Учетная запись", self.message.last_answer.args[0])

        self.message.answer.reset_mock()
        await show_account(self.message, self.repository, self.state)
        text = self.message.last_answer.args[0]
        for expected in ("1001", "Анна", "не указан", "02.01.2025"):
            self.assertIn(expected, text)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            account_menu_keyboard(),
        )

    async def test_phone_and_name_input_prompts(self):
        await request_phone(self.message, self.state)
        self.assertTrue(phone_request_keyboard().keyboard[0][0].request_contact)
        await request_name(self.message, self.state)
        self.assertIn("64 символов", self.message.last_answer.args[0])

    async def test_only_own_contact_can_change_phone(self):
        self.message.contact = SimpleNamespace(
            user_id=2002,
            phone_number="+79990000000",
        )
        await save_phone(self.message, self.state)
        self.repository.update_phone.assert_not_awaited()

        self.message.contact.user_id = 1001
        with patch(
            "flamenco_bot.keyboards.user.account.secrets.randbelow",
            return_value=123456,
        ), patch("flamenco_bot.keyboards.user.account.time.time", return_value=100):
            await save_phone(self.message, self.state)
            self.repository.update_phone.assert_not_awaited()
            self.assertEqual(
                self.state.current_state,
                AccountForm.waiting_for_phone_code.state,
            )
            self.assertIn("123456", self.message.last_answer.args[0])
            self.assertEqual(
                self.state.data["phone_code_hash"],
                hashlib.sha256(b"123456").hexdigest(),
            )

            self.message.text = "000000"
            await verify_phone_code(self.message, self.state, self.repository)
            self.repository.update_phone.assert_not_awaited()

            self.message.text = "123456"
            await verify_phone_code(self.message, self.state, self.repository)
        self.repository.update_phone.assert_awaited_once_with(1001, "+79990000000")

    async def test_phone_code_expires_and_limits_attempts(self):
        await self.state.set_state(AccountForm.waiting_for_phone_code)
        self.state.data.update(
            phone_code_hash=hashlib.sha256(b"123456").hexdigest(),
            phone_code_expires_at=time.time() - 1,
            phone_code_attempts=0,
            pending_phone="+79990000000",
        )
        await verify_phone_code(self.message, self.state, self.repository)
        self.repository.update_phone.assert_not_awaited()
        self.assertIsNone(self.state.current_state)
        self.assertIn("истёк", self.message.last_answer.args[0])

        await self.state.set_state(AccountForm.waiting_for_phone_code)
        self.state.data.update(
            phone_code_hash=hashlib.sha256(b"123456").hexdigest(),
            phone_code_expires_at=time.time() + 60,
            phone_code_attempts=0,
            pending_phone="+79990000000",
        )
        self.message.text = "000000"
        for _ in range(5):
            await verify_phone_code(self.message, self.state, self.repository)

        self.repository.update_phone.assert_not_awaited()
        self.assertIsNone(self.state.current_state)
        self.assertIn("Лимит попыток", self.message.last_answer.args[0])

    async def test_name_validation_and_update(self):
        self.message.text = "   "
        await save_name(self.message, self.state, self.repository)
        self.repository.update_user_name.assert_not_awaited()

        self.message.text = "Новое имя"
        await save_name(self.message, self.state, self.repository)
        self.repository.update_user_name.assert_awaited_once_with(1001, "Новое имя")

    async def test_account_back_clears_fsm(self):
        await return_from_account(self.message, self.state, self.repository)
        self.state.clear.assert_awaited_once()
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            main_menu_keyboard(),
        )

    async def test_booking_and_purchase_workflows_store_requests(self):
        await choose_class(self.message, self.state)
        self.message.text = "Фламенко для начинающих"
        await select_class(self.message, self.state)
        self.assertEqual(self.state.data["class_name"], self.message.text)

        self.message.text = "по будням вечером"
        await submit_booking_request(self.message, self.state, self.repository)
        self.repository.create_lesson_request.assert_awaited_with(
            telegram_id=1001,
            kind="booking",
            details="Фламенко для начинающих; пожелания по времени: по будням вечером",
        )
        self.assertIn("Запись пока не подтверждена", self.message.last_answer.args[0])
        self.repository.create_lesson_request.reset_mock()

        self.message.text = "Разовое занятие — 1000 ₽"
        await select_purchase(self.message, self.state)
        gateway = SimpleNamespace(is_configured=False)
        await submit_purchase_request(
            self.message,
            self.state,
            self.repository,
            gateway,
        )
        self.repository.create_lesson_request.assert_not_awaited()
        self.assertIn("Оплата недоступна", self.message.last_answer.args[0])

    async def test_purchase_creates_payment_link_and_confirms_paid_credits(self):
        self.message.text = "Разовое занятие — 1000 ₽"
        await select_purchase(self.message, self.state)
        provider_payment = ProviderPayment(
            payment_id="provider-payment-1",
            status="pending",
            amount_minor=100000,
            currency="RUB",
            confirmation_url="https://pay.example.test/confirm/1",
            metadata={"telegram_id": "1001", "package_key": "single"},
        )
        gateway = SimpleNamespace(
            is_configured=True,
            create_payment=AsyncMock(return_value=provider_payment),
            get_payment=AsyncMock(
                return_value=ProviderPayment(
                    payment_id="provider-payment-1",
                    status="succeeded",
                    amount_minor=100000,
                    currency="RUB",
                    confirmation_url=None,
                    metadata={"telegram_id": "1001", "package_key": "single"},
                )
            ),
        )
        await submit_purchase_request(
            self.message,
            self.state,
            self.repository,
            gateway,
        )
        gateway.create_payment.assert_awaited_once()
        self.repository.create_lesson_payment.assert_awaited_once_with(
            telegram_id=1001,
            package_key="single",
            lessons=1,
            amount_minor=100000,
            provider_payment_id="provider-payment-1",
            confirmation_url="https://pay.example.test/confirm/1",
        )
        inline_markup = self.message.last_answer.kwargs["reply_markup"]
        callback_data = inline_markup.inline_keyboard[1][0].callback_data
        self.assertEqual(callback_data, "lesson_payment_check:8")

        self.repository.get_lesson_payment.return_value = LessonPayment(
            id=8,
            telegram_id=1001,
            package_key="single",
            lessons=1,
            amount_minor=100000,
            provider_payment_id="provider-payment-1",
            confirmation_url="https://pay.example.test/confirm/1",
            status="pending",
        )
        callback = SimpleNamespace(
            data=callback_data,
            from_user=SimpleNamespace(id=1001),
            message=self.message,
            answer=AsyncMock(),
        )
        await check_lesson_payment(callback, self.repository, gateway)

        self.repository.complete_lesson_payment.assert_awaited_once_with(8, 1001)
        self.assertIn("Оплата подтверждена", self.message.last_answer.args[0])
        self.assertIn("Остаток: 1", self.message.last_answer.args[0])

    async def test_purchase_without_selected_package_falls_back(self):
        self.state.data = {}
        self.state.get_data = AsyncMock(return_value={})
        await submit_purchase_request(
            self.message,
            self.state,
            self.repository,
            SimpleNamespace(is_configured=False),
        )
        self.repository.create_lesson_request.assert_not_awaited()
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            purchase_menu_keyboard(),
        )

    async def test_lesson_cancel_and_back_clear_fsm(self):
        await self.state.set_state(LessonForm.waiting_for_booking_time)
        await cancel_lesson_flow(self.message, self.state, self.repository)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            class_menu_keyboard(),
        )
        await return_from_lessons(self.message, self.state, self.repository)
        self.assertEqual(self.state.clear.await_count, 2)

    async def test_lesson_back_buttons_return_to_expected_menu(self):
        await back_to_classes(self.message, self.state)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            class_menu_keyboard(),
        )
        await back_to_purchase_menu(self.message, self.state)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            purchase_menu_keyboard(),
        )
        await back_to_lessons_menu(self.message, self.state)
        self.assertEqual(
            self.message.last_answer.kwargs["reply_markup"],
            lessons_menu_keyboard(),
        )

    async def test_fallback_is_clear_and_actionable(self):
        await fallback_message(self.message, self.repository)
        self.assertIn("/help", self.message.last_answer.args[0])

    async def test_admin_commands_are_access_controlled(self):
        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_profile.return_value = self.repository.profile
        await admin_command(self.message, self.state, self.repository)
        self.assertEqual(
            {
                button.text
                for row in self.message.last_answer.kwargs["reply_markup"].keyboard
                for button in row
            },
            {
                "🔎 Найти участника",
                "✏️ Изменить имя участника",
                "📱 Изменить телефон участника",
                "🏠 Главное меню",
            },
        )
        await list_requests(self.message, self.repository)
        self.repository.list_pending_requests.assert_awaited_once()
        await complete_request(FakeMessage(text="/done bad"), self.repository)
        self.repository.complete_request.assert_not_awaited()
        await complete_request(FakeMessage(text="/done 7"), self.repository)
        self.repository.complete_request.assert_awaited_once_with(7)

        self.repository.profile = replace(self.repository.profile, is_admin=False)
        self.repository.get_profile.return_value = self.repository.profile
        await admin_command(self.message, self.state, self.repository)
        await list_requests(self.message, self.repository)
        self.assertEqual(self.repository.list_pending_requests.await_count, 1)

    async def test_admin_can_search_and_edit_participants(self):
        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_profile.return_value = self.repository.profile
        with patch("flamenco_bot.handlers.admin.actions_logger") as audit_logger:
            await start_participant_search(self.message, self.state, self.repository)
            self.assertEqual(self.state.current_state, AdminForm.waiting_for_search.state)
            self.message.text = "Анна"
            await search_participants(self.message, self.state, self.repository)
            self.repository.search_profiles.assert_awaited_once_with("Анна", limit=20)
            self.assertIn("1001", self.message.last_answer.args[0])

            await start_edit_participant_name(self.message, self.state, self.repository)
            self.message.text = "1001"
            await select_name_target(self.message, self.state, self.repository)
            self.message.text = "Новое имя"
            await save_participant_name(self.message, self.state, self.repository)
            self.repository.update_user_name.assert_awaited_once_with(1001, "Новое имя")

            await start_edit_participant_phone(self.message, self.state, self.repository)
            self.message.text = "1001"
            await select_phone_target(self.message, self.state, self.repository)
            self.message.text = "+79991234567"
            await save_participant_phone(self.message, self.state, self.repository)
            self.repository.update_phone.assert_awaited_once_with(
                1001,
                "+79991234567",
            )
            self.assertEqual(audit_logger.info.call_count, 3)

    async def test_non_admin_cannot_search_or_edit_participants(self):
        await start_participant_search(self.message, self.state, self.repository)
        self.message.text = "Анна"
        await search_participants(self.message, self.state, self.repository)
        self.repository.search_profiles.assert_not_awaited()
        self.assertIsNone(self.state.current_state)

    async def test_admin_empty_request_list(self):
        self.repository.list_pending_requests = AsyncMock(return_value=[])

        self.repository.profile = replace(self.repository.profile, is_admin=True)
        self.repository.get_profile.return_value = self.repository.profile
        await list_requests(self.message, self.repository)
        self.assertIn("нет", self.message.last_answer.args[0])

    async def test_command_registry_contains_supported_commands(self):
        commands = {command.command for command in get_bot_commands()}
        self.assertTrue(
            {
                "start",
                "account",
                "lessons",
                "schedule",
                "buy",
                "cancel",
                "admin",
                "requests",
                "done",
            }.issubset(commands)
        )
