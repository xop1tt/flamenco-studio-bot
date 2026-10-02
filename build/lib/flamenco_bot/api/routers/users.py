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

from fastapi import APIRouter, Depends

from ...database.repository import WebUserRecord
from ..dependencies import get_repository, require_telegram_linked_user
from ..schemas import ProfileResponse, UpdateProfileNameRequest


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
