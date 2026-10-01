from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class LessonPackage:
    key: str
    title: str
    lessons: int
    price_rub: int

    @property
    def menu_label(self) -> str:
        return "{} — {} ₽".format(self.title, self.price_rub)


# Replace these sample amounts before enabling payments with live credentials.
PURCHASE_PACKAGES: Dict[str, LessonPackage] = {
    "Разовое занятие": LessonPackage("single", "Разовое занятие", 1, 1000),
    "Абонемент на 4 занятия": LessonPackage(
        "pack_4", "Абонемент на 4 занятия", 4, 3600
    ),
    "Абонемент на 8 занятий": LessonPackage(
        "pack_8", "Абонемент на 8 занятий", 8, 6800
    ),
}
PURCHASE_OPTIONS = {
    package.menu_label: package for package in PURCHASE_PACKAGES.values()
}
