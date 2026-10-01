from typing import Sequence, Union

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


MAIN_MENU = "🏠 Главное меню"
CANCEL = "❌ Отмена"


def keyboard(*rows: Sequence[Union[str, KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                button
                if isinstance(button, KeyboardButton)
                else KeyboardButton(text=button)
                for button in row
            ]
            for row in rows
        ],
        resize_keyboard=True,
    )
