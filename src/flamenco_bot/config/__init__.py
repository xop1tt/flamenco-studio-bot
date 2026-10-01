"""Модуль конфигурации"""

import os
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


def parse_admins(value: str) -> list[int]:
    admins = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            telegram_id = int(item)
        except ValueError as error:
            raise ValueError("ADMINS должен содержать только числовые Telegram ID") from error
        if telegram_id <= 0:
            raise ValueError("Telegram ID администраторов должны быть положительными")
        if telegram_id not in admins:
            admins.append(telegram_id)
    return admins


def parse_database_pool_sizes(min_size: str, max_size: str) -> tuple[int, int]:
    try:
        minimum = int(min_size)
        maximum = int(max_size)
    except ValueError as error:
        raise ValueError(
            "DATABASE_POOL_MIN_SIZE и DATABASE_POOL_MAX_SIZE должны быть целыми числами"
        ) from error
    if minimum < 1 or maximum < minimum:
        raise ValueError(
            "Размер пула PostgreSQL должен удовлетворять "
            "1 <= DATABASE_POOL_MIN_SIZE <= DATABASE_POOL_MAX_SIZE"
        )
    return minimum, maximum


class Config:
    """Конфигурация бота"""

    # Токен бота
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # Администраторы
    ADMINS: list[int] = parse_admins(os.getenv("ADMINS", ""))

    # Окружение
    ENV: str = os.getenv("ENV", "development").strip().lower()
    if ENV not in {"development", "production"}:
        raise ValueError("ENV должен быть development или production")

    # PostgreSQL: строка подключения передается только через окружение.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    DATABASE_SSL_CA: Optional[str] = os.getenv("DATABASE_SSL_CA", "").strip() or None
    DATABASE_SSL_MODE: str = (
        os.getenv("DATABASE_SSL_MODE", "verify-full").strip().lower()
    )
    if DATABASE_SSL_MODE not in {"verify-full", "disable"}:
        raise ValueError("DATABASE_SSL_MODE должен быть verify-full или disable")
    if ENV == "production" and DATABASE_SSL_MODE != "verify-full":
        raise ValueError("В production DATABASE_SSL_MODE должен быть verify-full")
    DATABASE_POOL_MIN_SIZE, DATABASE_POOL_MAX_SIZE = parse_database_pool_sizes(
        os.getenv("DATABASE_POOL_MIN_SIZE", "1"),
        os.getenv("DATABASE_POOL_MAX_SIZE", "10"),
    )
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "").strip()
    YOOKASSA_SECRET_KEY: str = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
    YOOKASSA_RETURN_URL: str = os.getenv(
        "YOOKASSA_RETURN_URL",
        "https://t.me/",
    ).strip()

    # Если токен не задан - ошибка
    if not BOT_TOKEN:
        raise ValueError("⚠️ BOT_TOKEN не указан! Получи его от @BotFather")