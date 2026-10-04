"""Каталог направлений занятий: ``/api/classes``.

Источник истины — ``class_catalog`` (тот же каталог, которым пользуется бот).
Фронтенд получает название, описание и уровень отсюда вместо того, чтобы
хардкодить их отдельно (см. ``frontend/src/lib/directions.ts``).
"""

from typing import List

from fastapi import APIRouter

from ...class_catalog import CLASS_DESCRIPTIONS, CLASS_LABELS, CLASS_LEVELS
from ..schemas import ClassFormatResponse


router = APIRouter(prefix="/api/classes", tags=["classes"])


@router.get("", response_model=List[ClassFormatResponse])
async def list_classes() -> List[ClassFormatResponse]:
    return [
        ClassFormatResponse(
            key=key,
            label=label,
            description=CLASS_DESCRIPTIONS[key],
            level=CLASS_LEVELS[key],
        )
        for key, label in CLASS_LABELS.items()
    ]
