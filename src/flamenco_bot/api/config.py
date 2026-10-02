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

    # ЮKassa у бота и у сайта использует одни и те же YOOKASSA_SHOP_ID /
    # YOOKASSA_SECRET_KEY (одна организация, один магазин), но return_url
    # обязан различаться: бот возвращает пользователя в Telegram-чат
    # (BotConfig.YOOKASSA_RETURN_URL), а оплата, начатая на сайте, должна
    # вернуть пользователя на сайт, а не в бота. Пусто по умолчанию —
    # checkout на сайте остаётся недоступен (YooKassaClient.is_configured
    # == False), пока не укажете реальный адрес сайта здесь.
    WEB_YOOKASSA_RETURN_URL: str = os.getenv("WEB_YOOKASSA_RETURN_URL", "").strip()
