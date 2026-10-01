import logging
from typing import Any

from aiogram import Router
from aiogram.types import Message

from ..runtime.admin_access import get_admin_id
from ..keyboards.user import main_menu_keyboard


logger = logging.getLogger("bot.handlers.fallback")
router = Router(name="fallback")


@router.message()
async def fallback_message(message: Message, repository: Any) -> None:
    await message.answer(
        "Не распознал запрос. Используйте кнопки меню или команду /help.",
        reply_markup=main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        ),
    )
    logger.info(
        "Handled fallback telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )
