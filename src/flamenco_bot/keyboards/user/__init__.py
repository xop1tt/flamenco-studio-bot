"""Подписи кнопок и reply-клавиатуры клиентской части бота.

Навигация:
- главное меню (reply) — шесть разделов, всегда под рукой;
- внутри разделов «Записаться», «Мои занятия», «Абонементы» — inline-экраны
  в одном сообщении, «⬅️ Назад» возвращает на предыдущий экран;
- ввод текста (имя, телефон, обращение) — reply-клавиатура
  [❌ Отмена] (вернуться в раздел, откуда начат ввод) и [🏠 Главное меню].

Термины едины с сайтом: «Записаться», «Мои занятия», «Абонементы»,
«Баланс: N занятий», «Профиль», «Помощь», «Направление».
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from ..admin import ADMIN_MENU, BOT_MANAGEMENT_MENU
from ..common import CANCEL, MAIN_MENU, keyboard


BOOK = "🗓 Записаться"
MY_CLASSES = "📖 Мои занятия"
PACKAGES = "💳 Абонементы"
ABOUT = "💃 О студии"
PROFILE = "👤 Профиль"
HELP = "💬 Помощь"
PROFILE_NAME = "✏️ Изменить имя"
PROFILE_PHONE = "📱 Изменить телефон"
SEND_PHONE = "📲 Отправить мой номер"

# Подписи прежней версии меню. Reply-клавиатура остаётся у пользователя до
# тех пор, пока бот не пришлёт новую, поэтому после обновления люди ещё
# какое-то время нажимают старые кнопки — они ведут в новые разделы.
LEGACY_TO_SECTION = {
    "👤 Учетная запись": PROFILE,
    "📋 Показать мои данные": PROFILE,
    "📱 Изменить номер телефона": PROFILE_PHONE,
    "💃 Запись на занятия": BOOK,
    "🗓️ Записаться на занятие": BOOK,
    "📅 Расписание": BOOK,
    "⬅️ Назад к выбору занятия": BOOK,
    "💳 Покупка занятий": PACKAGES,
    "⬅️ Назад к выбору пакета": PACKAGES,
    "🆘 Обратиться в поддержку": HELP,
    "📚 О студии": ABOUT,
    "⬅️ Назад к занятиям": MAIN_MENU,
}


def main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[BOOK, MY_CLASSES], [PACKAGES, ABOUT], [PROFILE, HELP]]
    if is_admin:
        rows.append([ADMIN_MENU])
        rows.append([BOT_MANAGEMENT_MENU])
    return keyboard(*rows)


def profile_keyboard() -> ReplyKeyboardMarkup:
    return keyboard([PROFILE_NAME, PROFILE_PHONE], [MAIN_MENU])


def input_keyboard() -> ReplyKeyboardMarkup:
    return keyboard([CANCEL], [MAIN_MENU])


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [KeyboardButton(text=SEND_PHONE, request_contact=True)],
        [CANCEL],
        [MAIN_MENU],
    )


__all__ = [
    "ABOUT",
    "BOOK",
    "CANCEL",
    "HELP",
    "LEGACY_TO_SECTION",
    "MAIN_MENU",
    "MY_CLASSES",
    "PACKAGES",
    "PROFILE",
    "PROFILE_NAME",
    "PROFILE_PHONE",
    "SEND_PHONE",
    "input_keyboard",
    "main_menu_keyboard",
    "phone_request_keyboard",
    "profile_keyboard",
]
