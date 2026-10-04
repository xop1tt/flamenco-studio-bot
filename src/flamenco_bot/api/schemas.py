"""Pydantic-схемы запросов/ответов веб-API.

Явные схемы вместо прямой отдачи объектов репозитория — ``password_hash`` и
другие внутренние поля никогда не попадают в ответ.
"""

from datetime import datetime
from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field

from ..class_catalog import CLASS_LABELS
from ..database.repository import (
    ClassBooking,
    ClassSlot,
    LessonPaymentHistoryItem,
    SupportTicket,
    UserBooking,
    UserProfile,
    WebUserRecord,
)
from ..payments import LessonPackage
from ..services import CheckoutResult, SupportSubmission


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class TelegramAuthRequest(BaseModel):
    """Данные, которые Telegram Login Widget передаёт фронтенду.

    Подпись (``hash``) проверяется на backend — см. ``services.auth``.
    """

    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

    def to_payload(self) -> Mapping[str, Any]:
        return self.model_dump(exclude_none=True)


class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    telegram_id: Optional[int]
    display_name: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: WebUserRecord) -> "UserResponse":
        return cls(
            id=record.id,
            email=record.email,
            telegram_id=record.telegram_id,
            display_name=record.display_name,
            created_at=record.created_at,
        )


class ClassSlotResponse(BaseModel):
    id: int
    class_key: str
    class_label: str
    starts_at: datetime
    capacity: int
    remaining: int
    status: str

    @classmethod
    def from_record(cls, slot: ClassSlot) -> "ClassSlotResponse":
        return cls(
            id=slot.id,
            class_key=slot.class_key,
            class_label=CLASS_LABELS[slot.class_key],
            starts_at=slot.starts_at,
            capacity=slot.capacity,
            remaining=slot.remaining,
            status=slot.status,
        )


class ClassFormatResponse(BaseModel):
    """Направление занятий из ``class_catalog`` — того же каталога, которым
    пользуется бот: название, описание и уровень. Фронтенд ничего из этого
    не хардкодит (см. ``frontend/src/lib/directions.ts``).
    """

    key: str
    label: str
    description: str
    level: str


class LessonPackageResponse(BaseModel):
    key: str
    title: str
    lessons: int
    price_rub: int

    @classmethod
    def from_package(cls, package: LessonPackage) -> "LessonPackageResponse":
        return cls(
            key=package.key,
            title=package.title,
            lessons=package.lessons,
            price_rub=package.price_rub,
        )


class BookingRequest(BaseModel):
    slot_id: int = Field(gt=0)


class BookingResponse(BaseModel):
    id: int
    slot_id: int
    class_key: str
    class_label: str
    starts_at: datetime
    already_booked: bool

    @classmethod
    def from_booking(cls, booking: ClassBooking) -> "BookingResponse":
        return cls(
            id=booking.id,
            slot_id=booking.slot_id,
            class_key=booking.class_key,
            class_label=CLASS_LABELS[booking.class_key],
            starts_at=booking.starts_at,
            already_booked=booking.already_booked,
        )


class UserBookingResponse(BaseModel):
    id: int
    slot_id: int
    class_key: str
    class_label: str
    starts_at: datetime
    booking_status: str
    slot_status: str

    @classmethod
    def from_record(cls, booking: UserBooking) -> "UserBookingResponse":
        return cls(
            id=booking.id,
            slot_id=booking.slot_id,
            class_key=booking.class_key,
            class_label=CLASS_LABELS[booking.class_key],
            starts_at=booking.starts_at,
            booking_status=booking.booking_status,
            slot_status=booking.slot_status,
        )


class SupportMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class SupportSubmissionResponse(BaseModel):
    ticket_id: int
    created: bool
    admins_notified: bool

    @classmethod
    def from_submission(
        cls, submission: SupportSubmission
    ) -> "SupportSubmissionResponse":
        return cls(
            ticket_id=submission.ticket_id,
            created=submission.created,
            admins_notified=submission.notifications.complete,
        )


class SupportTicketResponse(BaseModel):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    last_message: str

    @classmethod
    def from_record(cls, ticket: SupportTicket) -> "SupportTicketResponse":
        return cls(
            id=ticket.id,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            last_message=ticket.last_message,
        )


class ProfileResponse(BaseModel):
    """Данные профиля из ``bot_users`` — те же, что видит сам бот в /account.

    Не путать с ``UserResponse``: это данные веб-аккаунта (``users``),
    а это — данные привязанного Telegram-профиля (баланс занятий и т.д.).
    """

    telegram_id: int
    user_name: str
    phone: Optional[str]
    lesson_credits: int
    registered_at: datetime
    is_admin: bool

    @classmethod
    def from_record(cls, profile: UserProfile) -> "ProfileResponse":
        return cls(
            telegram_id=profile.telegram_id,
            user_name=profile.user_name,
            phone=profile.phone,
            lesson_credits=profile.lesson_credits,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
        )


class UpdateProfileNameRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=64)


class CheckoutRequest(BaseModel):
    package_key: str = Field(min_length=1, max_length=64)


class CheckoutResponse(BaseModel):
    payment_id: int
    package_key: str
    amount_minor: int
    # None, если провайдер не вернул безопасную HTTPS-ссылку — см.
    # services.payments.safe_confirmation_url. Фронтенд должен сам решить,
    # что показать пользователю в этом случае (не редиректить на пустоту).
    confirmation_url: Optional[str]

    @classmethod
    def from_result(cls, result: CheckoutResult) -> "CheckoutResponse":
        return cls(
            payment_id=result.payment.id,
            package_key=result.package_key,
            amount_minor=result.amount_minor,
            confirmation_url=result.confirmation_url,
        )


class PaymentStatusResponse(BaseModel):
    status: str
    credits: Optional[int] = None


class PaymentHistoryItemResponse(BaseModel):
    id: int
    package_key: str
    package_title: str
    lessons: int
    amount_minor: int
    status: str
    created_at: datetime

    @classmethod
    def from_record(
        cls, item: LessonPaymentHistoryItem
    ) -> "PaymentHistoryItemResponse":
        return cls(
            id=item.id,
            package_key=item.package_key,
            package_title=item.package_title,
            lessons=item.lessons,
            amount_minor=item.amount_minor,
            status=item.status,
            created_at=item.created_at,
        )
