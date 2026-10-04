"""Время студии: единое место перевода моментов из PostgreSQL в пояс студии.

В БД время хранится как TIMESTAMPTZ (UTC). Всё, что видит человек — бот,
уведомления администраторам, сроки отмены, — показывается в
``Config.STUDIO_TIMEZONE`` через ``zoneinfo`` (правила пояса, включая
возможный переход на летнее время, а не ручное смещение).
"""

from datetime import datetime

from .config import Config


def to_studio_time(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Ожидается время с часовым поясом (TIMESTAMPTZ)")
    return moment.astimezone(Config.STUDIO_TIMEZONE)


def format_studio_datetime(moment: datetime) -> str:
    """«08.10.2026 19:00 MSK» — полная дата для администраторов."""
    return to_studio_time(moment).strftime("%d.%m.%Y %H:%M %Z")


def parse_studio_datetime(value: str, fmt: str) -> datetime:
    """Время, введённое администратором без пояса, — время студии."""
    return datetime.strptime(value, fmt).replace(tzinfo=Config.STUDIO_TIMEZONE)
