"""Единые правила отображения данных клиенту в боте.

Только форматирование: бизнес-правила (окно отмены, списание занятий)
живут в репозитории и сервисах, здесь лишь показываются пользователю.

Время: момент времени показывается как есть, без перевода в часовой пояс
студии — он ещё не определён (см. аудит, раздел о часовых поясах). Когда
пояс будет известен, перевод добавляется в ``format_class_time`` и
применяется ко всем клиентским сообщениям сразу.
"""

from datetime import datetime, timezone
from typing import Optional, Sequence

from .config import Config
from .database.repository import BOOKING_CANCELLATION_DEADLINE


WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def plural(count: int, forms: Sequence[str]) -> str:
    """Русское склонение: forms = ("занятие", "занятия", "занятий")."""
    value = abs(count) % 100
    if 11 <= value <= 14:
        return forms[2]
    value %= 10
    if value == 1:
        return forms[0]
    if 2 <= value <= 4:
        return forms[1]
    return forms[2]


LESSON_FORMS = ("занятие", "занятия", "занятий")
PLACE_FORMS = ("место", "места", "мест")


def lessons_count(count: int) -> str:
    return "{} {}".format(count, plural(count, LESSON_FORMS))


def balance_line(credits: int) -> str:
    return "Баланс: {}".format(lessons_count(credits))


def format_class_time(moment: datetime, now: Optional[datetime] = None) -> str:
    """«Вт 14.10 · 19:00»; год добавляется, только если он не текущий."""
    current = now or datetime.now(timezone.utc)
    date_format = "%d.%m" if moment.year == current.year else "%d.%m.%Y"
    return "{} {} · {}".format(
        WEEKDAYS[moment.weekday()],
        moment.strftime(date_format),
        moment.strftime("%H:%M"),
    )


def format_price(rubles: int) -> str:
    return "{:,} ₽".format(rubles).replace(",", " ")


def cancellation_deadline(starts_at: datetime) -> datetime:
    return starts_at - BOOKING_CANCELLATION_DEADLINE


def can_cancel(starts_at: datetime, now: Optional[datetime] = None) -> bool:
    """Подсказка для интерфейса; окончательно решает репозиторий."""
    current = now or datetime.now(timezone.utc)
    return current < cancellation_deadline(starts_at)


def cancellation_hint(starts_at: datetime, now: Optional[datetime] = None) -> str:
    if can_cancel(starts_at, now):
        return "Отменить запись можно до {}.".format(
            format_class_time(cancellation_deadline(starts_at), now)
        )
    return "Отменить эту запись уже нельзя — до начала меньше 24 часов."


def website_line(prefix: str = "Сайт студии") -> str:
    """Ссылка на сайт, если WEBSITE_URL задан (иначе пустая строка)."""
    url = Config.WEBSITE_URL
    return "{}: {}".format(prefix, url) if url else ""
