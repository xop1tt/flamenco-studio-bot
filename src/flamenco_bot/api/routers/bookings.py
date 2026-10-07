"""Запись на занятия: ``/api/bookings``.

Тонкая обёртка над ``services.booking.BookingService`` — вместимость,
повторная запись и гонки за последнее место проверяет репозиторий
транзакционно (см. ``PostgresRepository.book_class_slot``), сервис и этот
роутер не дублируют эту проверку. Запись и отмена с сайта ставят
участнику уведомление в Telegram (outbox, отправка после commit).
"""

import logging
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...database.repository import (
    BookingCooldownError,
    BookingNotFoundError,
    CancellationWindowExpiredError,
    InsufficientLessonCreditsError,
    SlotUnavailableError,
    WebUserRecord,
)
from ...services import BookingService, HistoryService
from ...services.history import booking_status
from ...services.profile import upcoming_bookings
from ..dependencies import (
    get_booking_service,
    get_history_service,
    require_telegram_linked_user,
)
from ..schemas import (
    BookingRequest,
    BookingResponse,
    BookingRulesResponse,
    UserBookingResponse,
)


logger = logging.getLogger("bot.api.bookings")
router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.get("/rules", response_model=BookingRulesResponse)
async def booking_rules() -> BookingRulesResponse:
    """Окно отмены и пауза повторной записи — публично, без авторизации."""
    return BookingRulesResponse.current()


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    try:
        booking = await booking_service.book(
            payload.slot_id, current_user.telegram_id, notify_user=True
        )
    except (
        SlotUnavailableError,
        InsufficientLessonCreditsError,
        BookingCooldownError,
    ) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    if not booking.already_booked:
        await booking_service.notify_admins_about_booking(
            booking, current_user.display_name
        )
    return BookingResponse.from_booking(booking)


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_booking(
    slot_id: int,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> None:
    try:
        await booking_service.cancel(
            slot_id, current_user.telegram_id, notify_user=True
        )
    except BookingNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except CancellationWindowExpiredError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.get("/me", response_model=List[UserBookingResponse])
async def list_my_bookings(
    scope: Literal["all", "upcoming", "past"] = Query(default="all"),
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    history_service: HistoryService = Depends(get_history_service),
) -> List[UserBookingResponse]:
    """Записи участника: все (по умолчанию, как раньше), предстоящие
    действующие (``upcoming``, от ближайшей) или прошедшие и отменённые
    (``past``)."""
    bookings = await history_service.bookings(
        current_user.telegram_id, limit=100, offset=0
    )
    if scope == "upcoming":
        bookings = upcoming_bookings(bookings)
    elif scope == "past":
        bookings = [item for item in bookings if booking_status(item) != "upcoming"]
    return [UserBookingResponse.from_record(booking) for booking in bookings]
