import logging
from pathlib import Path
from typing import Any, Optional

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.methods import Response, TelegramMethod

from .logging_utils import RetentionRotatingFileHandler
from .paths import get_log_directory


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
    logger = logging.getLogger("bot.answers")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    target_directory = log_directory or get_log_directory()
    target_directory.mkdir(parents=True, exist_ok=True)
    target_file = (target_directory / "answers_log").resolve()
    if not any(
        getattr(handler, "baseFilename", None) == str(target_file)
        for handler in logger.handlers
    ):
        handler = RetentionRotatingFileHandler(
            target_file,
            encoding="utf-8",
            maxBytes=5_000_000,
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)

    return logger


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
