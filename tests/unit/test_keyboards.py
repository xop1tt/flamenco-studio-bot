import unittest

from flamenco_bot.handlers import router as bot_router
from flamenco_bot.keyboards.admin import (
    BOT_CANCEL_SCHEDULED_RESTART,
    BOT_SCHEDULE_RESTART,
    bot_management_keyboard,
)
from flamenco_bot.keyboards.user.account import router as account_keyboard_router
from flamenco_bot.keyboards.user.lessons import router as lessons_keyboard_router
from flamenco_bot.keyboards.user.main_menu import router as main_menu_keyboard_router
from flamenco_bot.keyboards.user import (
    account_menu_keyboard,
    cancel_keyboard,
    class_menu_keyboard,
    lessons_menu_keyboard,
    main_menu_keyboard,
    phone_request_keyboard,
    purchase_menu_keyboard,
    booking_input_keyboard,
    purchase_confirmation_keyboard,
)


class KeyboardTests(unittest.TestCase):
    def test_all_menu_builders_return_reply_keyboards(self):
        for builder in (
            main_menu_keyboard,
            account_menu_keyboard,
            lessons_menu_keyboard,
            class_menu_keyboard,
            purchase_menu_keyboard,
            phone_request_keyboard,
            cancel_keyboard,
            booking_input_keyboard,
            purchase_confirmation_keyboard,
        ):
            with self.subTest(builder=builder.__name__):
                self.assertTrue(builder().keyboard)

    def test_main_menu_contains_account_and_lessons(self):
        labels = {
            button.text
            for row in main_menu_keyboard().keyboard
            for button in row
        }
        self.assertEqual(labels, {"👤 Учетная запись", "💃 Запись на занятия"})

    def test_admin_menu_button_is_only_in_admin_main_menu(self):
        admin_labels = {
            button.text
            for row in main_menu_keyboard(is_admin=True).keyboard
            for button in row
        }
        regular_labels = {
            button.text
            for row in main_menu_keyboard().keyboard
            for button in row
        }
        self.assertIn("🛠 Админ-меню", admin_labels)
        self.assertIn("⚙️ Управление ботом", admin_labels)
        self.assertNotIn("🛠 Админ-меню", regular_labels)
        self.assertNotIn("⚙️ Управление ботом", regular_labels)

    def test_bot_management_menu_contains_restart_schedule_actions(self):
        labels = {
            button.text
            for row in bot_management_keyboard().keyboard
            for button in row
        }
        self.assertIn(BOT_SCHEDULE_RESTART, labels)
        self.assertIn(BOT_CANCEL_SCHEDULED_RESTART, labels)

    def test_account_keyboard_contains_edit_actions_and_back(self):
        labels = {
            button.text
            for row in account_menu_keyboard().keyboard
            for button in row
        }
        self.assertIn("📱 Изменить номер телефона", labels)
        self.assertIn("✏️ Изменить имя", labels)
        self.assertIn("📋 Показать мои данные", labels)
        self.assertIn("🏠 Главное меню", labels)

    def test_submenus_have_back_and_home_navigation(self):
        for builder, back_label in (
            (class_menu_keyboard, "⬅️ Назад к занятиям"),
            (purchase_menu_keyboard, "⬅️ Назад к занятиям"),
            (booking_input_keyboard, "⬅️ Назад к выбору занятия"),
            (purchase_confirmation_keyboard, "⬅️ Назад к выбору пакета"),
        ):
            labels = {
                button.text
                for row in builder().keyboard
                for button in row
            }
            with self.subTest(builder=builder.__name__):
                self.assertIn(back_label, labels)
                self.assertIn("🏠 Главное меню", labels)

    def test_phone_keyboard_requests_contact(self):
        contact_button = phone_request_keyboard().keyboard[0][0]
        self.assertTrue(contact_button.request_contact)

    def test_keyboard_handlers_precede_wildcard_fsm_handlers(self):
        account_names = [
            handler.callback.__name__
            for handler in account_keyboard_router.message.handlers
        ]
        lesson_names = [
            handler.callback.__name__
            for handler in lessons_keyboard_router.message.handlers
        ]
        main_menu_names = [
            handler.callback.__name__
            for handler in main_menu_keyboard_router.message.handlers
        ]
        self.assertLess(
            account_names.index("request_name"),
            account_names.index("save_phone"),
        )
        self.assertLess(
            lesson_names.index("select_purchase"),
            lesson_names.index("submit_booking_request"),
        )
        self.assertLess(
            lesson_names.index("back_to_classes"),
            lesson_names.index("submit_booking_request"),
        )
        self.assertLess(
            lesson_names.index("back_to_purchase_menu"),
            lesson_names.index("submit_purchase_request"),
        )
        self.assertIn("cancel_from_menu", main_menu_names)
        self.assertIn("back_to_lessons_menu", main_menu_names)

        router_names = [child.name for child in bot_router.sub_routers]
        self.assertLess(
            router_names.index("admin_commands"),
            router_names.index("account_keyboard"),
        )
