import logging
from pathlib import Path
from typing import Any, Optional

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.methods import Response, TelegramMethod

from .logging_utils import create_file_logger


MESSAGE_METHODS = {
    "sendMessage",
    "editMessageText",
    "sendPhoto",
    "sendDocument",
    "sendVideo",
    "sendAudio",
    "sendVoice",
    "sendAnimation",
    "sendVideoNote",
    "sendSticker",
    "sendLocation",
    "sendVenue",
    "sendContact",
    "sendPoll",
    "sendDice",
    "sendInvoice",
    "sendMediaGroup",
    "editMessageCaption",
    "answerCallbackQuery",
}


def create_answers_logger(log_directory: Optional[Path] = None) -> logging.Logger:
    return create_file_logger("bot.answers", "answers_log", log_directory)


class AnswersLogMiddleware(BaseRequestMiddleware):
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Response[Any]:
        result = await make_request(bot, method)
        api_method = method.__api_method__

        if api_method in MESSAGE_METHODS:
            text = getattr(method, "text", None) or getattr(method, "caption", None)
            self.logger.info(
                "method=%s payload_chars=%s",
                api_method,
                len(text) if text else 0,
            )

        return result
