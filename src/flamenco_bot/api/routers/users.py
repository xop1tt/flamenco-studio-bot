"""Профиль и баланс занятий: ``/api/users/me/profile``.

Данные (``bot_users``: телефон, баланс занятий, дата регистрации) — те же,
что бот показывает по /account; отдельного "веб-профиля" с этими полями нет.
Требует привязанного Telegram — см. ``require_telegram_linked_user``.

Изменение телефона сюда намеренно не входит: в боте оно подтверждается
одноразовым кодом через Telegram-контакт (``keyboards/user/account.py``),
и для сайта пока нет эквивалентной проверки владения номером — см.
Follow-up в отчёте по этому этапу.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ...database.repository import WebUserRecord
from ...services import NotificationService, ProfileService
from ..dependencies import (
    get_notification_service,
    get_profile_service,
    get_repository,
    require_telegram_linked_user,
)
from ..schemas import (
    NotificationSettingsResponse,
    OverviewResponse,
    ProfileResponse,
    UpdateNotificationSettingsRequest,
    UpdateProfileNameRequest,
)


logger = logging.getLogger("bot.api.users")
router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/profile", response_model=ProfileResponse)
async def read_my_profile(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    repository: Any = Depends(get_repository),
) -> ProfileResponse:
    profile = await repository.get_profile(current_user.telegram_id)
    return ProfileResponse.from_record(profile)


@router.patch("/me/profile", response_model=ProfileResponse)
async def update_my_profile_name(
    payload: UpdateProfileNameRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    repository: Any = Depends(get_repository),
) -> ProfileResponse:
    await repository.update_user_name(current_user.telegram_id, payload.user_name)
    profile = await repository.get_profile(current_user.telegram_id)
    return ProfileResponse.from_record(profile)


@router.get("/me/overview", response_model=OverviewResponse)
async def read_my_overview(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    profile_service: ProfileService = Depends(get_profile_service),
) -> OverviewResponse:
    """Профиль, баланс по абонементам, ближайшие занятия, непрочитанные
    уведомления — та же сводка, что «👤 Профиль» в боте."""
    try:
        overview = await profile_service.overview(current_user.telegram_id)
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Профиль не найден") from error
    return OverviewResponse.from_overview(overview)


@router.get("/me/notification-settings", response_model=NotificationSettingsResponse)
async def read_notification_settings(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationSettingsResponse:
    return NotificationSettingsResponse.from_settings(
        await service.settings(current_user.telegram_id)
    )


@router.patch("/me/notification-settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    payload: UpdateNotificationSettingsRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationSettingsResponse:
    """Отключить можно только напоминания и сообщение о малом остатке —
    об отмене/переносе занятия и изменении баланса бот сообщает всегда."""
    return NotificationSettingsResponse.from_settings(
        await service.update_settings(
            current_user.telegram_id,
            reminders=payload.reminders,
            low_balance=payload.low_balance,
        )
    )
