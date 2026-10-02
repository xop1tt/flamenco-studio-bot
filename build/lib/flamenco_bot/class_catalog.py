from typing import Sequence

from .database.repository import ClassSlot


CLASS_LABELS = {
    "beginner": "Фламенко для начинающих",
    "intermediate": "Продолжающая группа",
    "individual": "Индивидуальное занятие",
}

CLASS_KEYS_BY_LABEL = {label: key for key, label in CLASS_LABELS.items()}


def format_class_schedule(slots: Sequence[ClassSlot]) -> str:
    available = [slot for slot in slots if slot.status == "open" and slot.remaining]
    if not available:
        return (
            "Сейчас нет свободных слотов. Вы можете обратиться в поддержку "
            "или проверить расписание позже."
        )
    lines = ["Свободные занятия:"]
    lines.extend(
        "• {} — {} (свободно {})".format(
            CLASS_LABELS[slot.class_key],
            slot.starts_at.strftime("%d.%m.%Y %H:%M %Z"),
            slot.remaining,
        )
        for slot in available
    )
    return "\n".join(lines)
