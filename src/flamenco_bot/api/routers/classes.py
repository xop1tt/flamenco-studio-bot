"""Каталог форматов занятий: ``/api/classes``.

Источник истины — ``class_catalog.CLASS_LABELS``, тот же словарь, которым
пользуется бот. Фронтенд получает ``key``/``label`` отсюда вместо того, чтобы
хардкодить их отдельно (см. комментарий в ``frontend/src/lib/directions.ts``).
"""

from typing import List

from fastapi import APIRouter

from ...class_catalog import CLASS_LABELS
from ..schemas import ClassFormatResponse


router = APIRouter(prefix="/api/classes", tags=["classes"])


@router.get("", response_model=List[ClassFormatResponse])
async def list_classes() -> List[ClassFormatResponse]:
    return [
        ClassFormatResponse(key=key, label=label) for key, label in CLASS_LABELS.items()
    ]
