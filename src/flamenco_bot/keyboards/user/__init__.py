from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from ..admin import ADMIN_MENU, BOT_MANAGEMENT_MENU
from ..common import CANCEL, MAIN_MENU, keyboard
from ...payments.catalog import PURCHASE_PACKAGES


ACCOUNT_MENU = "👤 Учетная запись"
SHOW_MY_DATA = "📋 Показать мои данные"
ACCOUNT_NAME = "✏️ Изменить имя"
ACCOUNT_PHONE = "📱 Изменить номер телефона"
LESSONS_MENU = "💃 Запись на занятия"
BOOK_CLASS = "🗓️ Записаться на занятие"
BUY_LESSONS = "💳 Покупка занятий"
SCHEDULE = "📅 Расписание"
BACK_TO_LESSONS = "⬅️ Назад к занятиям"
BACK_TO_CLASSES = "⬅️ Назад к выбору занятия"
BACK_TO_PURCHASES = "⬅️ Назад к выбору пакета"


def main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [[ACCOUNT_MENU], [LESSONS_MENU]]
    if is_admin:
        rows.append([ADMIN_MENU])
        rows.append([BOT_MANAGEMENT_MENU])
    return keyboard(*rows)


def account_menu_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [SHOW_MY_DATA],
        [ACCOUNT_PHONE],
        [ACCOUNT_NAME],
        [MAIN_MENU],
    )


def lessons_menu_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [BOOK_CLASS],
        [SCHEDULE],
        [BUY_LESSONS],
        [MAIN_MENU],
    )


def class_menu_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        ["Фламенко для начинающих"],
        ["Продолжающая группа"],
        ["Индивидуальное занятие"],
        [BACK_TO_LESSONS],
        [MAIN_MENU],
    )


def purchase_menu_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        *[[package.menu_label] for package in PURCHASE_PACKAGES.values()],
        [BACK_TO_LESSONS],
        [MAIN_MENU],
    )


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [KeyboardButton(text="📲 Отправить мой номер", request_contact=True)],
        [CANCEL],
        [MAIN_MENU],
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return keyboard([CANCEL], [MAIN_MENU])


def booking_input_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [BACK_TO_CLASSES],
        [CANCEL],
        [MAIN_MENU],
    )


def purchase_confirmation_keyboard() -> ReplyKeyboardMarkup:
    return keyboard(
        [BACK_TO_PURCHASES],
        [CANCEL],
        [MAIN_MENU],
    )


__all__ = [
    "ACCOUNT_MENU",
    "ACCOUNT_NAME",
    "ACCOUNT_PHONE",
    "BACK_TO_CLASSES",
    "BACK_TO_LESSONS",
    "BACK_TO_PURCHASES",
    "BOOK_CLASS",
    "BUY_LESSONS",
    "CANCEL",
    "LESSONS_MENU",
    "MAIN_MENU",
    "SCHEDULE",
    "SHOW_MY_DATA",
    "account_menu_keyboard",
    "booking_input_keyboard",
    "cancel_keyboard",
    "class_menu_keyboard",
    "lessons_menu_keyboard",
    "main_menu_keyboard",
    "phone_request_keyboard",
    "purchase_confirmation_keyboard",
    "purchase_menu_keyboard",
]
