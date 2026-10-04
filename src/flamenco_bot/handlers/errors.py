"""Глобальная обработка недоступной PostgreSQL в боте.

Без этого обработчика любое действие при упавшей БД заканчивалось молча:
исключение попадало в лог, пользователь не получал ответа, а нажатая
inline-кнопка оставалась "в загрузке". Подробности ошибки — только в логе
(их уже пишет ``UpdateLoggingMiddleware``), пользователю — общее сообщение.
"""

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from ..database import is_database_unavailable


logger = logging.getLogger("bot.handlers.errors")
router = Router(name="errors")

SERVICE_UNAVAILABLE_TEXT = (
    "Сервис временно недоступен. Попробуйте ещё раз через несколько минут."
)


def _database_unavailable(event: ErrorEvent) -> bool:
    return is_database_unavailable(event.exception)


@router.error(_database_unavailable)
async def database_unavailable(event: ErrorEvent) -> None:
    update = event.update
    callback = update.callback_query
    message = update.message
    source = callback or message
    sender = source.from_user if source is not None else None
    logger.error(
        "Database unavailable while handling update update_id=%s "
        "telegram_id=%s error_type=%s",
        update.update_id,
        sender.id if sender else None,
        type(event.exception).__name__,
    )
    try:
        if callback is not None:
            await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        elif message is not None:
            await message.answer(SERVICE_UNAVAILABLE_TEXT)
    except TelegramAPIError as error:
        logger.warning(
            "Failed to notify user about unavailable database error_type=%s",
            type(error).__name__,
        )
