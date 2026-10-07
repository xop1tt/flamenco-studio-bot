"""Уведомления участника на сайте: ``/api/notifications``.

Та же таблица, из которой бот рассылает уведомления в Telegram (outbox
``user_notifications``): лента, счётчик непрочитанных, «прочитано».
Тексты — из ``notification_texts``, как и в боте.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ...database.repository import WebUserRecord
from ...services import NotificationService
from ..dependencies import get_notification_service, require_telegram_linked_user
from ..schemas import (
    MAX_DB_ID,
    MarkNotificationsReadRequest,
    MarkNotificationsReadResponse,
    NotificationResponse,
    NotificationsPage,
    UnreadCountResponse,
)


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/me", response_model=NotificationsPage)
async def list_my_notifications(
    limit: int = Query(default=20, ge=1, le=50),
    unread_only: bool = Query(default=False),
    before_id: Optional[int] = Query(default=None, gt=0, le=MAX_DB_ID),
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationsPage:
    items = list(
        await service.feed(
            current_user.telegram_id,
            limit=limit + 1,
            unread_only=unread_only,
            before_id=before_id,
        )
    )
    has_more = len(items) > limit
    items = items[:limit]
    return NotificationsPage(
        items=[NotificationResponse.from_notification(item) for item in items],
        unread_count=await service.unread_count(current_user.telegram_id),
        next_before_id=items[-1].id if has_more and items else None,
    )


@router.get("/me/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    return UnreadCountResponse(
        unread_count=await service.unread_count(current_user.telegram_id)
    )


@router.post("/me/read", response_model=MarkNotificationsReadResponse)
async def mark_read(
    payload: MarkNotificationsReadRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    service: NotificationService = Depends(get_notification_service),
) -> MarkNotificationsReadResponse:
    """Отмечает прочитанными только свои уведомления: чужие id игнорируются."""
    updated = await service.mark_read(current_user.telegram_id, payload.ids)
    return MarkNotificationsReadResponse(updated=updated)
