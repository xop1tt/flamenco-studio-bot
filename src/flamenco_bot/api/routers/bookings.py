"""Запись на занятия: ``/api/bookings``.

Тонкая обёртка над ``services.booking.BookingService`` — вместимость,
повторная запись и гонки за последнее место проверяет репозиторий
транзакционно (см. ``PostgresRepository.book_class_slot``), сервис и этот
роутер не дублируют эту проверку.
"""

import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from ...database.repository import SlotUnavailableError, WebUserRecord
from ...services import BookingService
from ..dependencies import (
    get_booking_service,
    get_repository,
    require_telegram_linked_user,
)
from ..schemas import BookingRequest, BookingResponse, UserBookingResponse


logger = logging.getLogger("bot.api.bookings")
router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingResponse:
    try:
        booking = await booking_service.book(payload.slot_id, current_user.telegram_id)
    except SlotUnavailableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    if not booking.already_booked:
        await booking_service.notify_admins_about_booking(
            booking, current_user.display_name
        )
    return BookingResponse.from_booking(booking)


@router.get("/me", response_model=List[UserBookingResponse])
async def list_my_bookings(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    repository: Any = Depends(get_repository),
) -> List[UserBookingResponse]:
    bookings = await repository.list_bookings_for_telegram_id(current_user.telegram_id)
    return [UserBookingResponse.from_record(booking) for booking in bookings]
