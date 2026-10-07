"""Публичное расписание занятий: ``/api/schedule``.

Не требует авторизации — та же информация, что бот показывает по /schedule.
Отменённые студией занятия в общем списке не показываются; карточка
занятия по id отдаёт его в любом статусе (например, чтобы страница
занятия из старой ссылки показала «Отменено»).
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
    available_only: bool = Query(default=False),
    repository: Any = Depends(get_repository),
) -> List[ClassSlotResponse]:
    if class_key is not None and class_key not in CLASS_KEYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Неизвестный формат занятия"
        )
    slots = await repository.list_class_slots(class_key=class_key, limit=100)
    items = [ClassSlotResponse.from_record(slot) for slot in slots]
    if available_only:
        items = [item for item in items if item.bookable]
    return items


@router.get("/{slot_id}", response_model=ClassSlotResponse)
async def read_slot(
    slot_id: int,
    repository: Any = Depends(get_repository),
) -> ClassSlotResponse:
    slot = await repository.get_class_slot(slot_id) if slot_id > 0 else None
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Занятие не найдено")
    return ClassSlotResponse.from_record(slot)
