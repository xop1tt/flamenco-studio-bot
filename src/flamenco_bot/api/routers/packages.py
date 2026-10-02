"""Каталог абонементов: ``/api/packages``.

Источник истины — ``payments.catalog.PURCHASE_PACKAGES``, тот же каталог,
которым пользуется бот при продаже занятий. Цены не дублируются во фронтенде.
"""

from typing import List

from fastapi import APIRouter

from ...payments import PURCHASE_PACKAGES
from ..schemas import LessonPackageResponse


router = APIRouter(prefix="/api/packages", tags=["packages"])


@router.get("", response_model=List[LessonPackageResponse])
async def list_packages() -> List[LessonPackageResponse]:
    return [
        LessonPackageResponse.from_package(package)
        for package in PURCHASE_PACKAGES.values()
    ]
