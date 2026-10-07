"""История: операции с балансом и записи на занятия — ``/api/history``.

Финансовая история — это ledger (``lesson_credit_ledger``) с понятным типом
операции и подписью (``services.history``) — те же строки, что «🧾
Операции» в боте. Пагинация курсором: ``before_id`` из ``next_before_id``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ...database.repository import WebUserRecord
from ...services import HistoryService
from ..dependencies import get_history_service, require_telegram_linked_user
from ..schemas import (
    BookingHistoryPage,
    HistoryOperationResponse,
    HistoryOperationsPage,
    UserBookingResponse,
)


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/operations", response_model=HistoryOperationsPage)
async def list_operations(
    limit: int = Query(default=20, ge=1, le=50),
    before_id: Optional[int] = Query(default=None, gt=0),
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    history_service: HistoryService = Depends(get_history_service),
) -> HistoryOperationsPage:
    operations = list(
        await history_service.operations(
            current_user.telegram_id, limit=limit + 1, before_id=before_id
        )
    )
    has_more = len(operations) > limit
    operations = operations[:limit]
    return HistoryOperationsPage(
        items=[HistoryOperationResponse.from_operation(item) for item in operations],
        next_before_id=operations[-1].entry.id if has_more and operations else None,
    )


@router.get("/classes", response_model=BookingHistoryPage)
async def list_class_history(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    history_service: HistoryService = Depends(get_history_service),
) -> BookingHistoryPage:
    bookings = list(
        await history_service.bookings(
            current_user.telegram_id, limit=limit + 1, offset=offset
        )
    )
    has_more = len(bookings) > limit
    return BookingHistoryPage(
        items=[UserBookingResponse.from_record(item) for item in bookings[:limit]],
        next_offset=offset + limit if has_more else None,
    )
