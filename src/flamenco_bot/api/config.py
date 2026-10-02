"""Конфигурация веб-процесса — поверх общего конфига бота.

Веб-API и бот используют один и тот же ``.env`` (БД, BOT_TOKEN для проверки
подписи Telegram Login Widget, ЮKassa). Этот класс лишь добавляет то, что
нужно только веб-слою: секрет подписи сессионных cookie. ``Config`` бота
(``..config.Config``) не изменяется, чтобы не менять поведение и требования
запуска Telegram-бота.
"""

import os

from ..config import Config as BotConfig


class WebConfig(BotConfig):
    """Конфигурация FastAPI-приложения сайта."""

    SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "").strip()

    if not SESSION_SECRET_KEY:
        raise ValueError(
            "⚠️ SESSION_SECRET_KEY не указан! Сгенерируйте случайный секрет "
            "для подписи веб-сессий, например:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
