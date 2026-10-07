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
CREDITS_ADJUST_CONFIRM = "✅ Применить корректировку"
CREDITS_ADJUST_CANCEL = "↩️ Не применять"
ADMIN_SCHEDULE = "🗓 Расписание занятий"
ADMIN_CLIENTS = "👥 Клиенты"
ADMIN_FINANCE = "💰 Финансы"
SUPPORT_TICKETS = "📨 Обращения поддержки"
# Кнопки прежнего админ-меню: старая reply-клавиатура может остаться у
# администратора — они по-прежнему работают (поиск, имя/телефон по ID,
# расписание), но в новом меню эти действия — в карточке участника.
CLASS_SLOTS = "🗓 Слоты занятий"


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Четыре раздела; действия внутри — inline-кнопками в карточках."""
    return keyboard(
        [ADMIN_SCHEDULE, ADMIN_CLIENTS],
        [SUPPORT_TICKETS, ADMIN_FINANCE],
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


def credit_adjustment_confirmation_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [CREDITS_ADJUST_CONFIRM],
        [CREDITS_ADJUST_CANCEL],
        [MAIN_MENU],
    )
