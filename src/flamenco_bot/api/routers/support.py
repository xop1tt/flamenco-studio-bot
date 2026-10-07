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
    SupportThreadResponse,
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
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error
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


@router.get("/me/{ticket_id}", response_model=SupportThreadResponse)
async def read_my_support_ticket(
    ticket_id: int,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    repository: Any = Depends(get_repository),
) -> SupportThreadResponse:
    """Переписка по своему обращению (вопрос, ответы студии, закрытие).

    Чужое обращение — 404, как и несуществующее: id не раскрывают, есть ли
    такое обращение у другого участника.
    """
    thread = await repository.get_support_ticket_thread(
        ticket_id, current_user.telegram_id
    )
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Обращение не найдено")
    return SupportThreadResponse.from_thread(thread)
