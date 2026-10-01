from aiogram.types import ReplyKeyboardMarkup

from ..common import CANCEL, MAIN_MENU, keyboard


ADMIN_MENU = "🛠 Админ-меню"
ADMIN_SEARCH = "🔎 Найти участника"
ADMIN_EDIT_NAME = "✏️ Изменить имя участника"
ADMIN_EDIT_PHONE = "📱 Изменить телефон участника"
BOT_MANAGEMENT_MENU = "⚙️ Управление ботом"
BOT_STATUS = "📊 Состояние бота"
BOT_RESTART = "🔄 Перезапустить бота"
BOT_RESTART_CONFIRM = "✅ Подтвердить перезапуск"
BOT_RESTART_CANCEL = "↩️ Не перезапускать"
BOT_SCHEDULE_RESTART = "🕒 Запланировать перезапуск"
BOT_CANCEL_SCHEDULED_RESTART = "❌ Отменить запланированный перезапуск"


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [ADMIN_SEARCH],
        [ADMIN_EDIT_NAME],
        [ADMIN_EDIT_PHONE],
        [MAIN_MENU],
    )


def admin_action_keyboard() -> ReplyKeyboardMarkup:
    return keyboard([ADMIN_MENU], [MAIN_MENU])


def bot_management_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [BOT_STATUS],
        [BOT_RESTART],
        [BOT_SCHEDULE_RESTART],
        [BOT_CANCEL_SCHEDULED_RESTART],
        [MAIN_MENU],
    )


def bot_restart_confirmation_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [BOT_RESTART_CONFIRM],
        [BOT_RESTART_CANCEL],
        [MAIN_MENU],
    )


def bot_schedule_input_keyboard() -> ReplyKeyboardMarkup:
    return keyboard([CANCEL], [MAIN_MENU])
