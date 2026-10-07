"""Время студии: единое место перевода моментов из PostgreSQL в пояс студии.

В БД время хранится как TIMESTAMPTZ (UTC). Всё, что видит человек — бот,
уведомления администраторам, сроки отмены, — показывается в
``Config.STUDIO_TIMEZONE`` через ``zoneinfo`` (правила пояса, включая
возможный переход на летнее время, а не ручное смещение).
"""

from datetime import datetime, timezone
from typing import Optional

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


_ADMIN_FORMATS = (
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%d.%m.%y %H:%M",
)


def parse_admin_datetime(value: str, now: Optional[datetime] = None) -> datetime:
    """Дата и время занятия, введённые администратором.

    Принимает «14.10 19:00» (ближайшее будущее 14 октября), «14.10.2026
    19:00», «2026-10-14 19:00» — во времени студии, — и ISO 8601 со смещением
    («2026-10-14T19:00+03:00», как в /slot_add). ``ValueError`` — формат не
    распознан.
    """
    text = " ".join(value.strip().replace("T", " ", 1).split())
    if not text:
        raise ValueError("Укажите дату и время, например 14.10 19:00")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        parsed = None
    if parsed is not None and parsed.tzinfo is not None:
        return parsed
    for fmt in _ADMIN_FORMATS:
        try:
            return parse_studio_datetime(text, fmt)
        except ValueError:
            continue
    try:
        partial = datetime.strptime(text, "%d.%m %H:%M")
    except ValueError as error:
        raise ValueError(
            "Не удалось распознать дату. Пример: 14.10 19:00 или 14.10.2026 19:00"
        ) from error
    current = to_studio_time(now or datetime.now(timezone.utc))
    candidate = partial.replace(year=current.year, tzinfo=Config.STUDIO_TIMEZONE)
    if candidate < current:
        candidate = candidate.replace(year=current.year + 1)
    return candidate
