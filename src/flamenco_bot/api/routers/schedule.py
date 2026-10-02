"""Публичное расписание занятий: ``/api/schedule``.

Не требует авторизации — та же информация, что бот показывает по /schedule.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...database.repository import CLASS_KEYS
from ..dependencies import get_repository
from ..schemas import ClassSlotResponse


router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("", response_model=List[ClassSlotResponse])
async def list_schedule(
    class_key: Optional[str] = Query(default=None),
    repository: Any = Depends(get_repository),
) -> List[ClassSlotResponse]:
    if class_key is not None and class_key not in CLASS_KEYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Неизвестный формат занятия"
        )
    slots = await repository.list_class_slots(class_key=class_key, limit=100)
    return [ClassSlotResponse.from_record(slot) for slot in slots]
