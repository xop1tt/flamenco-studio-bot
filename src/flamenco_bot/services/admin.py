"""Сводка для администратора: показатели студии за день и неделю.

«Сегодня» — календарный день в часовом поясе студии (STUDIO_TIMEZONE), как
и время занятий в боте и на сайте.
"""

from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from ..database.admin_queries import AdminDashboard
from ..studio_time import to_studio_time


class AdminService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    async def dashboard(self, now: Optional[datetime] = None) -> AdminDashboard:
        current = now or datetime.now(timezone.utc)
        local = to_studio_time(current)
        day_start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
        # Через смену часового пояса (переход на летнее время) — по календарю,
        # а не «+24 часа».
        day_end = datetime.combine(
            local.date() + timedelta(days=1), time.min, tzinfo=local.tzinfo
        )
        return await self.repository.get_admin_dashboard(
            day_start, day_end, current + timedelta(days=7)
        )
