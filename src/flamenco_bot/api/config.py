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


def parse_frontend_proxy_secret(value: str) -> str:
    secret = value.strip()
    if secret and len(secret) < 32:
        raise ValueError("FRONTEND_PROXY_SECRET должен быть не короче 32 символов")
    return secret


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

    # Общий секрет сайта и API для хостингов, где адрес прокси сайта заранее
    # неизвестен (Netlify → Render): сервер сайта передаёт IP посетителя в
    # X-Flamenco-Client-IP вместе с этим секретом, и rate limit входа
    # считает попытки по посетителю. Пусто — заголовок игнорируется, IP
    # берётся из соединения (FORWARDED_ALLOW_IPS, см. __main__.py).
    FRONTEND_PROXY_SECRET: str = parse_frontend_proxy_secret(
        os.getenv("FRONTEND_PROXY_SECRET", "")
    )
