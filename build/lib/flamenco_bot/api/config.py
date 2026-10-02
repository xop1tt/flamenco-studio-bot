"""Конфигурация веб-процесса — поверх общего конфига бота.

Веб-API и бот используют один и тот же ``.env`` (БД, BOT_TOKEN для проверки
подписи Telegram Login Widget, ЮKassa). ``Config`` бота (``..config.Config``)
не изменяется, чтобы не менять поведение и требования запуска Telegram-бота.

Сессии сайта не подписываются секретом: cookie несёт непрозрачный токен,
проверяемый по таблице ``web_sessions`` в БД (см. ``api/security.py``), так
что отдельный ``SESSION_SECRET_KEY`` сайту не нужен.
"""

import os

from ..config import Config as BotConfig


class WebConfig(BotConfig):
    """Конфигурация FastAPI-приложения сайта."""

    # ЮKassa у бота и у сайта использует одни и те же YOOKASSA_SHOP_ID /
    # YOOKASSA_SECRET_KEY (одна организация, один магазин), но return_url
    # обязан различаться: бот возвращает пользователя в Telegram-чат
    # (BotConfig.YOOKASSA_RETURN_URL), а оплата, начатая на сайте, должна
    # вернуть пользователя на сайт, а не в бота. Пусто по умолчанию —
    # checkout на сайте остаётся недоступен (YooKassaClient.is_configured
    # == False), пока не укажете реальный адрес сайта здесь.
    WEB_YOOKASSA_RETURN_URL: str = os.getenv("WEB_YOOKASSA_RETURN_URL", "").strip()
