"""Обращения в поддержку: ``/api/support``.

Тонкая обёртка над ``services.support.SupportService`` — та же очередь
тикетов, которую администраторы ведут в Telegram-боте.
"""

import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from ...database.repository import WebUserRecord
from ...services import (
    SupportMessageInvalidError,
    SupportRateLimitedError,
    SupportService,
)
from ..dependencies import (
    get_repository,
    get_support_service,
    require_telegram_linked_user,
)
from ..schemas import (
    SupportMessageRequest,
    SupportSubmissionResponse,
    SupportTicketResponse,
)


logger = logging.getLogger("bot.api.support")
router = APIRouter(prefix="/api/support", tags=["support"])


@router.post(
    "",
    response_model=SupportSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_support_message(
    payload: SupportMessageRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    support_service: SupportService = Depends(get_support_service),
) -> SupportSubmissionResponse:
    try:
        submission = await support_service.submit_message(
            telegram_id=current_user.telegram_id,
            user_name=current_user.display_name,
            body=payload.body,
        )
    except SupportMessageInvalidError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    except SupportRateLimitedError as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error
    return SupportSubmissionResponse.from_submission(submission)


@router.get("/me", response_model=List[SupportTicketResponse])
async def list_my_support_tickets(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    repository: Any = Depends(get_repository),
) -> List[SupportTicketResponse]:
    tickets = await repository.list_support_tickets_for_telegram_id(
        current_user.telegram_id
    )
    return [SupportTicketResponse.from_record(ticket) for ticket in tickets]
