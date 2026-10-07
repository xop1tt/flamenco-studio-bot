"""Абонементы: каталог ``/api/packages`` и мои абонементы ``/api/packages/me``.

Каталог — ``payments.catalog.PURCHASE_PACKAGES``, тот же, которым
пользуется бот при продаже занятий. Цены не дублируются во фронтенде.
Остатки по абонементам считает ``PackageService`` из ledger — та же
сводка, что «🎟 Абонементы» в боте.
"""

from typing import List

from fastapi import APIRouter, Depends

from ...database.repository import WebUserRecord
from ...payments import PURCHASE_PACKAGES
from ...services import PackageService
from ..dependencies import get_package_service, require_telegram_linked_user
from ..schemas import LessonPackageResponse, PackageSummaryResponse


router = APIRouter(prefix="/api/packages", tags=["packages"])


@router.get("", response_model=List[LessonPackageResponse])
async def list_packages() -> List[LessonPackageResponse]:
    return [
        LessonPackageResponse.from_package(package)
        for package in PURCHASE_PACKAGES.values()
    ]


@router.get("/me", response_model=PackageSummaryResponse)
async def my_packages(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    package_service: PackageService = Depends(get_package_service),
) -> PackageSummaryResponse:
    summary = await package_service.summary(current_user.telegram_id)
    return PackageSummaryResponse.from_summary(summary)
