"""In-memory реализация репозитория — без PostgreSQL.

Только для разработки и тестов: данные живут в памяти процесса и теряются
при остановке. В production бот и API без DATABASE_URL не стартуют
(main.py, api/app.py). Поведение повторяет ``PostgresRepository``
(repository.py), включая правила записи и платежей.
"""

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import ceil
from typing import AsyncIterator, Dict, Optional, Sequence, Tuple

from .admin_queries import InMemoryAdminMixin
from .repository import (
    BOOKING_REBOOK_COOLDOWN,
    BookingCooldownError,
    BookingNotFoundError,
    CLASS_KEYS,
    ClassBooking,
    ClassSlot,
    DatabaseHealth,
    EmailAlreadyRegisteredError,
    InsufficientLessonCreditsError,
    LessonPayment,
    LessonPaymentAttempt,
    LessonPaymentHistoryItem,
    LessonRefund,
    LessonRequest,
    PendingLessonPayment,
    SlotUnavailableError,
    SupportMessage,
    SupportTicket,
    TelegramAlreadyLinkedError,
    UserBooking,
    UserProfile,
    UserStatistics,
    WebUserRecord,
    check_cancellation_window,
    hash_session_token,
    logger,
    _validate_slot,
    _validate_support_body,
)
from .studio_memory import InMemoryStudioMixin


@dataclass(frozen=True)
class _StoredBooking:
    """Внутреннее состояние брони в ``InMemoryRepository``.

    Отдельный тип от ``ClassBooking``: тот — одноразовый результат вызова
    ``book_class_slot``, а здесь нужен настоящий статус (confirmed/cancelled)
    и момент последнего изменения — без него нельзя ни посчитать занятые
    места, ни проверить дедлайн отмены/кулдаун повторной записи.
    """

    id: int
    status: str
    updated_at: datetime
    # Момент последней записи (для правила отмены после переноса студией).
    booked_at: Optional[datetime] = None


class InMemoryRepository(InMemoryStudioMixin, InMemoryAdminMixin):
    """Temporary repository used only when PostgreSQL is not configured."""

    supports_durable_payments = False

    def __init__(self) -> None:
        self._profiles: Dict[int, UserProfile] = {}
        self._requests: Dict[int, LessonRequest] = {}
        self._payments: Dict[int, LessonPayment] = {}
        # LessonPayment (используется в checkout/сверке) не несёт created_at —
        # отдельный словарь только для list_lesson_payments_for_telegram_id.
        self._payment_created_at: Dict[int, datetime] = {}
        self._payment_attempts: Dict[Tuple[int, str], LessonPaymentAttempt] = {}
        self._credit_ledger: list[Tuple[int, int, str, Optional[int]]] = []
        self._class_slots: Dict[int, ClassSlot] = {}
        self._class_bookings: Dict[Tuple[int, int], _StoredBooking] = {}
        self._support_tickets: Dict[int, SupportTicket] = {}
        self._support_messages: Dict[int, list[SupportMessage]] = {}
        self._last_seen: Dict[int, datetime] = {}
        self._scheduled_restart_at: Optional[datetime] = None
        self._next_request_id = 1
        self._next_payment_id = 1
        self._next_slot_id = 1
        self._next_booking_id = 1
        self._next_support_ticket_id = 1
        self._web_users: Dict[int, WebUserRecord] = {}
        self._next_web_user_id = 1
        self._web_sessions: Dict[str, Tuple[int, datetime]] = {}
        self._advisory_locks: set[int] = set()
        self._init_studio_state()

    async def initialize(self) -> None:
        logger.warning("Using in-memory storage; data will be lost at shutdown")

    @asynccontextmanager
    async def try_advisory_lock(self, lock_id: int) -> AsyncIterator[bool]:
        if lock_id in self._advisory_locks:
            yield False
            return
        self._advisory_locks.add(lock_id)
        try:
            yield True
        finally:
            self._advisory_locks.discard(lock_id)

    async def close(self) -> None:
        logger.info("In-memory storage closed")

    async def health_check(self) -> DatabaseHealth:
        return DatabaseHealth(
            backend="memory",
            pool_size=0,
            idle_connections=0,
        )

    async def get_scheduled_restart(self) -> Optional[datetime]:
        return self._scheduled_restart_at

    async def set_scheduled_restart(self, scheduled_at: datetime) -> None:
        self._scheduled_restart_at = scheduled_at

    async def clear_scheduled_restart(self) -> None:
        self._scheduled_restart_at = None

    async def get_or_create_profile(
        self,
        telegram_id: int,
        user_name: str,
        is_admin: bool,
    ) -> UserProfile:
        profile = self._profiles.get(telegram_id)
        if profile is None:
            profile = UserProfile(
                telegram_id=telegram_id,
                phone=None,
                user_name=user_name,
                registered_at=datetime.now(timezone.utc),
                is_admin=is_admin,
            )
        else:
            profile = UserProfile(
                telegram_id=profile.telegram_id,
                phone=profile.phone,
                user_name=profile.user_name,
                registered_at=profile.registered_at,
                is_admin=profile.is_admin,
                lesson_credits=profile.lesson_credits,
            )
        self._profiles[telegram_id] = profile
        self._last_seen[telegram_id] = datetime.now(timezone.utc)
        return profile

    async def record_activity(self, telegram_id: int) -> None:
        if telegram_id in self._profiles:
            self._last_seen[telegram_id] = datetime.now(timezone.utc)

    async def get_user_statistics(self, online_since: datetime) -> UserStatistics:
        total_users = len(self._profiles)
        online_users = sum(
            last_seen >= online_since for last_seen in self._last_seen.values()
        )
        return UserStatistics(total_users, online_users)

    async def update_phone(self, telegram_id: int, phone: str) -> None:
        profile = self._get_profile(telegram_id)
        self._profiles[telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits,
        )

    async def update_user_name(self, telegram_id: int, user_name: str) -> None:
        profile = self._get_profile(telegram_id)
        self._profiles[telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits,
        )

    async def begin_lesson_payment_attempt(
        self,
        telegram_id: int,
        package_key: str,
        package_title: str,
        lessons: int,
        amount_minor: int,
    ) -> LessonPaymentAttempt:
        if telegram_id not in self._profiles:
            raise LookupError("Сначала создайте профиль командой /start")
        attempt_key = (telegram_id, package_key)
        existing = self._payment_attempts.get(attempt_key)
        if existing is not None and existing.status in {"creating", "pending"}:
            return existing
        attempt = LessonPaymentAttempt(
            idempotence_key=uuid.uuid4(),
            telegram_id=telegram_id,
            package_key=package_key,
            package_title=package_title,
            lessons=lessons,
            amount_minor=amount_minor,
            status="creating",
        )
        self._payment_attempts[attempt_key] = attempt
        return attempt

    async def create_lesson_payment(
        self,
        telegram_id: int,
        package_key: str,
        package_title: str,
        lessons: int,
        amount_minor: int,
        provider_payment_id: str,
        confirmation_url: str,
        idempotence_key: uuid.UUID,
    ) -> LessonPayment:
        if telegram_id not in self._profiles:
            raise LookupError("Сначала создайте профиль командой /start")
        payment = LessonPayment(
            id=self._next_payment_id,
            telegram_id=telegram_id,
            package_key=package_key,
            lessons=lessons,
            amount_minor=amount_minor,
            provider_payment_id=provider_payment_id,
            confirmation_url=confirmation_url,
            status="pending",
            package_title=package_title,
        )
        existing = next(
            (
                item
                for item in self._payments.values()
                if item.provider_payment_id == provider_payment_id
            ),
            None,
        )
        if existing is not None:
            return existing
        self._payments[payment.id] = payment
        self._payment_created_at[payment.id] = datetime.now(timezone.utc)
        self._next_payment_id += 1
        self._payment_attempts[(telegram_id, package_key)] = LessonPaymentAttempt(
            idempotence_key=idempotence_key,
            telegram_id=telegram_id,
            package_key=package_key,
            package_title=package_title,
            lessons=lessons,
            amount_minor=amount_minor,
            status="pending",
            provider_payment_id=provider_payment_id,
            confirmation_url=confirmation_url,
        )
        return payment

    async def get_lesson_payment(
        self,
        payment_id: int,
        telegram_id: int,
    ) -> Optional[LessonPayment]:
        payment = self._payments.get(payment_id)
        if payment is None or payment.telegram_id != telegram_id:
            return None
        return payment

    async def complete_lesson_payment(
        self,
        payment_id: int,
        telegram_id: int,
    ) -> bool:
        payment = await self.get_lesson_payment(payment_id, telegram_id)
        if payment is None or payment.status != "pending":
            return False
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="succeeded",
            package_title=payment.package_title,
        )
        attempt_key = (payment.telegram_id, payment.package_key)
        attempt = self._payment_attempts.get(attempt_key)
        if (
            attempt is not None
            and attempt.provider_payment_id == payment.provider_payment_id
        ):
            self._payment_attempts[attempt_key] = LessonPaymentAttempt(
                idempotence_key=attempt.idempotence_key,
                telegram_id=attempt.telegram_id,
                package_key=attempt.package_key,
                package_title=attempt.package_title,
                lessons=attempt.lessons,
                amount_minor=attempt.amount_minor,
                status="completed",
                provider_payment_id=attempt.provider_payment_id,
                confirmation_url=attempt.confirmation_url,
            )
        self._append_ledger(telegram_id, payment.lessons, "purchase", payment.id)
        profile = self._get_profile(telegram_id)
        self._profiles[telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits + payment.lessons,
        )
        return True

    async def cancel_lesson_payment(self, payment_id: int, telegram_id: int) -> bool:
        payment = await self.get_lesson_payment(payment_id, telegram_id)
        if payment is None or payment.status != "pending":
            return False
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="canceled",
            package_title=payment.package_title,
        )
        attempt_key = (payment.telegram_id, payment.package_key)
        attempt = self._payment_attempts.get(attempt_key)
        if (
            attempt is not None
            and attempt.provider_payment_id == payment.provider_payment_id
        ):
            self._payment_attempts[attempt_key] = LessonPaymentAttempt(
                idempotence_key=attempt.idempotence_key,
                telegram_id=attempt.telegram_id,
                package_key=attempt.package_key,
                package_title=attempt.package_title,
                lessons=attempt.lessons,
                amount_minor=attempt.amount_minor,
                status="failed",
                provider_payment_id=attempt.provider_payment_id,
                confirmation_url=attempt.confirmation_url,
            )
        return True

    async def prepare_lesson_refund(
        self,
        payment_id: int,
        admin_telegram_id: int,
        reason: str,
    ) -> Optional[LessonRefund]:
        _ = admin_telegram_id
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 300:
            raise ValueError("Причина возврата должна содержать от 1 до 300 символов")
        payment = self._payments.get(payment_id)
        if payment is None:
            return None
        if payment.status == "refund_pending":
            return LessonRefund(
                payment_id=payment.id,
                telegram_id=payment.telegram_id,
                provider_payment_id=payment.provider_payment_id,
                amount_minor=payment.amount_minor,
                lessons=payment.lessons,
                idempotence_key=payment.refund_idempotence_key or uuid.uuid4(),
                provider_refund_id=payment.provider_refund_id,
                reason=payment.refund_reason or normalized_reason,
            )
        if payment.status != "succeeded":
            return None
        profile = self._get_profile(payment.telegram_id)
        payment_credit_balance = self._payment_credit_balance(payment_id)
        if (
            profile.lesson_credits < payment.lessons
            or payment_credit_balance < payment.lessons
        ):
            raise ValueError("Недостаточно неиспользованных занятий для возврата")
        refund_key = uuid.uuid4()
        self._profiles[payment.telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits - payment.lessons,
        )
        self._append_ledger(
            payment.telegram_id, -payment.lessons, "refund_reservation", payment_id
        )
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="refund_pending",
            refund_idempotence_key=refund_key,
            refund_reason=normalized_reason,
        )
        return LessonRefund(
            payment_id=payment.id,
            telegram_id=payment.telegram_id,
            provider_payment_id=payment.provider_payment_id,
            amount_minor=payment.amount_minor,
            lessons=payment.lessons,
            idempotence_key=refund_key,
            provider_refund_id=None,
            reason=normalized_reason,
        )

    async def record_provider_refund(
        self,
        payment_id: int,
        provider_refund_id: str,
    ) -> None:
        payment = self._payments[payment_id]
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status=payment.status,
            refund_idempotence_key=payment.refund_idempotence_key,
            provider_refund_id=provider_refund_id,
            refund_reason=payment.refund_reason,
        )

    async def complete_lesson_refund(self, payment_id: int) -> bool:
        payment = self._payments.get(payment_id)
        if payment is None or payment.status != "refund_pending":
            return False
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="refunded",
            refund_idempotence_key=payment.refund_idempotence_key,
            provider_refund_id=payment.provider_refund_id,
            refund_reason=payment.refund_reason,
        )
        self._credit_ledger = [
            row._replace(entry_type="refund")
            if row.payment_id == payment_id and row.entry_type == "refund_reservation"
            else row
            for row in self._credit_ledger
        ]
        return True

    async def release_lesson_refund(self, payment_id: int) -> bool:
        payment = self._payments.get(payment_id)
        if payment is None or payment.status != "refund_pending":
            return False
        profile = self._get_profile(payment.telegram_id)
        self._profiles[payment.telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits + payment.lessons,
        )
        self._append_ledger(
            payment.telegram_id, payment.lessons, "refund_release", payment_id
        )
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="succeeded",
            refund_reason=payment.refund_reason,
        )
        return True

    async def get_lesson_credits(self, telegram_id: int) -> int:
        return self._get_profile(telegram_id).lesson_credits

    async def list_lesson_payments_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 20,
    ) -> Sequence[LessonPaymentHistoryItem]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество платежей должно быть от 1 до 100")
        items = [
            LessonPaymentHistoryItem(
                id=payment.id,
                package_key=payment.package_key,
                package_title=payment.package_title,
                lessons=payment.lessons,
                amount_minor=payment.amount_minor,
                status=payment.status,
                created_at=self._payment_created_at.get(
                    payment.id, datetime.now(timezone.utc)
                ),
            )
            for payment in self._payments.values()
            if payment.telegram_id == telegram_id
        ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:limit]

    async def list_pending_lesson_payments_older_than(
        self,
        cutoff: datetime,
        limit: int = 200,
    ) -> Sequence[PendingLessonPayment]:
        items = [
            PendingLessonPayment(
                id=payment.id,
                telegram_id=payment.telegram_id,
                created_at=created_at,
            )
            for payment in self._payments.values()
            if payment.status == "pending"
            and (created_at := self._payment_created_at.get(payment.id)) is not None
            and created_at < cutoff
        ]
        items.sort(key=lambda item: item.created_at)
        return items[:limit]

    async def search_profiles(
        self,
        query: str,
        limit: int = 20,
    ) -> Sequence[UserProfile]:
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > 100:
            raise ValueError("Поисковый запрос должен содержать от 1 до 100 символов")
        if not 1 <= limit <= 100:
            raise ValueError("Количество профилей должно быть от 1 до 100")

        lowered_query = normalized_query.casefold()
        profiles = [
            profile
            for profile in self._profiles.values()
            if normalized_query == str(profile.telegram_id)
            or lowered_query in profile.user_name.casefold()
            or lowered_query in (profile.phone or "").casefold()
        ]
        profiles.sort(key=lambda profile: profile.registered_at, reverse=True)
        return profiles[:limit]

    async def get_profile(self, telegram_id: int) -> Optional[UserProfile]:
        return self._profiles.get(telegram_id)

    async def create_class_slot(
        self,
        class_key: str,
        starts_at: datetime,
        capacity: int,
        admin_telegram_id: int,
    ) -> ClassSlot:
        _validate_slot(class_key, starts_at, capacity)
        slot = ClassSlot(
            id=self._next_slot_id,
            class_key=class_key,
            starts_at=starts_at,
            capacity=capacity,
            booked_count=0,
        )
        self._class_slots[slot.id] = slot
        self._next_slot_id += 1
        self._record_slot_event(
            slot.id,
            "created",
            actor_telegram_id=admin_telegram_id,
            new_starts_at=starts_at,
            new_capacity=capacity,
        )
        logger.info(
            "Created in-memory class slot id=%s admin_id=%s",
            slot.id,
            admin_telegram_id,
        )
        return slot

    async def list_class_slots(
        self,
        class_key: Optional[str] = None,
        limit: int = 100,
        include_cancelled: bool = False,
        starts_after: Optional[datetime] = None,
    ) -> Sequence[ClassSlot]:
        if class_key is not None and class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        after = starts_after or datetime.now(timezone.utc)
        slots = [
            self._slot_with_count(slot)
            for slot in self._class_slots.values()
            if slot.starts_at > after
            and (class_key is None or slot.class_key == class_key)
            and (include_cancelled or slot.status != "cancelled")
        ]
        return sorted(slots, key=lambda slot: slot.starts_at)[:limit]

    async def list_available_class_slots(
        self,
        class_key: str,
        limit: int = 20,
    ) -> Sequence[ClassSlot]:
        if class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        slots = [
            slot
            for slot in await self.list_class_slots(class_key, limit=100)
            if slot.status == "open" and slot.remaining > 0
        ]
        return slots[:limit]

    async def book_class_slot(
        self,
        slot_id: int,
        telegram_id: int,
        notify_user: bool = False,
    ) -> ClassBooking:
        slot = self._class_slots.get(slot_id)
        if (
            slot is None
            or slot.status != "open"
            or slot.starts_at <= datetime.now(timezone.utc)
        ):
            raise SlotUnavailableError("Слот закрыт или уже недоступен")
        key = (slot_id, telegram_id)
        previous = self._class_bookings.get(key)
        if previous is not None and previous.status == "confirmed":
            return ClassBooking(
                id=previous.id,
                slot_id=slot_id,
                telegram_id=telegram_id,
                starts_at=slot.starts_at,
                class_key=slot.class_key,
                already_booked=True,
            )
        if previous is not None and previous.status == "cancelled":
            cooldown_ends_at = previous.updated_at + BOOKING_REBOOK_COOLDOWN
            now = datetime.now(timezone.utc)
            if now < cooldown_ends_at:
                hours_left = ceil((cooldown_ends_at - now).total_seconds() / 3600)
                raise BookingCooldownError(
                    "Повторная запись на это занятие после отмены "
                    "будет доступна через {} ч.".format(hours_left)
                )

        current_slot = self._slot_with_count(slot)
        if current_slot.booked_count >= current_slot.capacity:
            raise SlotUnavailableError("На это занятие уже нет свободных мест")

        profile = self._get_profile(telegram_id)
        if profile.lesson_credits <= 0:
            raise InsufficientLessonCreditsError(
                "На балансе нет доступных занятий. Купите абонемент, чтобы записаться."
            )

        source = self._memory_pick_source(telegram_id)
        booking_id = previous.id if previous is not None else self._next_booking_id
        if previous is None:
            self._next_booking_id += 1
        now = datetime.now(timezone.utc)
        self._class_bookings[key] = _StoredBooking(
            id=booking_id,
            status="confirmed",
            updated_at=now,
            booked_at=now,
        )
        balance = profile.lesson_credits - 1
        self._set_credits(telegram_id, balance)
        self._append_ledger(
            telegram_id,
            -1,
            "lesson_use",
            source.id if source is not None and source.kind == "payment" else None,
            grant_id=(
                source.id if source is not None and source.kind == "grant" else None
            ),
            booking_id=booking_id,
        )
        if source is not None:
            source = replace(source, remaining=max(0, source.remaining - 1))
        if notify_user:
            self._memory_enqueue(
                telegram_id,
                "booking_confirmed",
                {
                    "slot_id": slot_id,
                    "class_key": slot.class_key,
                    "starts_at": slot.starts_at.isoformat(),
                    "balance": balance,
                    "source_title": source.title if source else None,
                },
                "booking_confirmed:{}:{}".format(booking_id, uuid.uuid4()),
            )
        self._memory_enqueue_low_balance(telegram_id, balance)
        return ClassBooking(
            id=booking_id,
            slot_id=slot_id,
            telegram_id=telegram_id,
            starts_at=slot.starts_at,
            class_key=slot.class_key,
            balance=balance,
            source=source,
        )

    async def cancel_class_slot_booking(
        self,
        slot_id: int,
        telegram_id: int,
        notify_user: bool = False,
    ) -> bool:
        slot = self._class_slots.get(slot_id)
        if slot is None:
            raise BookingNotFoundError("Запись не найдена")
        key = (slot_id, telegram_id)
        booking = self._class_bookings.get(key)
        if booking is None:
            raise BookingNotFoundError("Запись не найдена")
        if booking.status != "confirmed":
            return False
        check_cancellation_window(
            slot.starts_at, booking.booked_at, slot.rescheduled_at
        )

        self._class_bookings[key] = replace(
            booking, status="cancelled", updated_at=datetime.now(timezone.utc)
        )
        balance = self._get_profile(telegram_id).lesson_credits + 1
        self._set_credits(telegram_id, balance)
        payment_id, grant_id = self._booking_source(booking.id)
        self._append_ledger(
            telegram_id,
            1,
            "adjustment",
            payment_id,
            grant_id=grant_id,
            booking_id=booking.id,
        )
        if notify_user:
            self._memory_enqueue(
                telegram_id,
                "booking_cancelled",
                {
                    "slot_id": slot_id,
                    "class_key": slot.class_key,
                    "starts_at": slot.starts_at.isoformat(),
                    "balance": balance,
                },
                "booking_cancelled:{}:{}".format(booking.id, uuid.uuid4()),
            )
        return True

    async def list_bookings_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[UserBooking]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество записей должно быть от 1 до 100")
        if offset < 0:
            raise ValueError("Смещение списка не может быть отрицательным")
        bookings = []
        for (slot_id, booking_telegram_id), booking in self._class_bookings.items():
            if booking_telegram_id != telegram_id:
                continue
            slot = self._class_slots[slot_id]
            cancelled_by = None
            if booking.status == "cancelled":
                cancelled_by = (
                    "studio"
                    if slot.status == "cancelled"
                    and slot.cancelled_at is not None
                    and booking.updated_at >= slot.cancelled_at
                    else "user"
                )
            moved = next(
                (
                    event
                    for event in reversed(self._slot_events)
                    if event.slot_id == slot_id and event.event_type == "rescheduled"
                ),
                None,
            )
            bookings.append(
                UserBooking(
                    id=booking.id,
                    slot_id=slot_id,
                    class_key=slot.class_key,
                    starts_at=slot.starts_at,
                    booking_status=booking.status,
                    slot_status=slot.status,
                    booked_at=booking.booked_at,
                    cancelled_by=cancelled_by,
                    rescheduled_at=slot.rescheduled_at,
                    previous_starts_at=moved.old_starts_at if moved else None,
                    slot_cancel_reason=slot.cancel_reason,
                )
            )
        bookings.sort(key=lambda item: (item.starts_at, item.id), reverse=True)
        return bookings[offset : offset + limit]

    async def update_class_slot_capacity(
        self,
        slot_id: int,
        capacity: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        if not 1 <= capacity <= 100:
            raise ValueError("Вместимость слота должна быть от 1 до 100")
        slot = self._class_slots.get(slot_id)
        if slot is None:
            return False
        if slot.status == "cancelled":
            raise ValueError("Занятие отменено — вместимость не меняется")
        current = self._slot_with_count(slot)
        if capacity < current.booked_count:
            raise ValueError(
                "Нельзя установить вместимость ниже числа подтверждённых записей"
            )
        self._class_slots[slot_id] = replace(
            slot, capacity=capacity, booked_count=current.booked_count
        )
        if capacity != slot.capacity:
            self._record_slot_event(
                slot_id,
                "capacity_changed",
                actor_telegram_id=admin_telegram_id,
                old_capacity=slot.capacity,
                new_capacity=capacity,
            )
        return True

    async def close_class_slot(
        self,
        slot_id: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        slot = self._class_slots.get(slot_id)
        if slot is None or slot.status != "open":
            return False
        self._class_slots[slot_id] = replace(slot, status="closed")
        self._record_slot_event(slot_id, "closed", actor_telegram_id=admin_telegram_id)
        return True

    def _slot_with_count(self, slot: ClassSlot) -> ClassSlot:
        booked_count = sum(
            1
            for (booking_slot_id, _), booking in self._class_bookings.items()
            if booking_slot_id == slot.id and booking.status == "confirmed"
        )
        return replace(slot, booked_count=booked_count)

    async def list_admin_ids(self) -> Sequence[int]:
        return sorted(
            profile.telegram_id
            for profile in self._profiles.values()
            if profile.is_admin
        )

    async def create_support_message(
        self,
        telegram_id: int,
        body: str,
    ) -> tuple[int, bool]:
        normalized = _validate_support_body(body)
        now = datetime.now(timezone.utc)
        ticket = next(
            (
                item
                for item in self._support_tickets.values()
                if item.telegram_id == telegram_id and item.status == "open"
            ),
            None,
        )
        created = ticket is None
        if ticket is None:
            ticket = SupportTicket(
                id=self._next_support_ticket_id,
                telegram_id=telegram_id,
                status="open",
                created_at=now,
                updated_at=now,
            )
            self._support_tickets[ticket.id] = ticket
            self._support_messages[ticket.id] = []
            self._next_support_ticket_id += 1
        self._support_messages[ticket.id].append(
            SupportMessage(ticket.id, telegram_id, "user", normalized, created_at=now)
        )
        self._support_tickets[ticket.id] = SupportTicket(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=now,
        )
        return ticket.id, created

    async def reply_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        body: str,
    ) -> Optional[int]:
        normalized = _validate_support_body(body)
        ticket = self._support_tickets.get(ticket_id)
        if ticket is None or ticket.status != "open":
            return None
        self._support_messages[ticket_id].append(
            SupportMessage(
                ticket_id,
                admin_telegram_id,
                "admin",
                normalized,
                created_at=datetime.now(timezone.utc),
            )
        )
        self._support_tickets[ticket_id] = SupportTicket(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=datetime.now(timezone.utc),
            last_message=normalized,
        )
        return ticket.telegram_id

    async def list_open_support_tickets(
        self,
        limit: int = 20,
    ) -> Sequence[SupportTicket]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество обращений должно быть от 1 до 100")
        tickets = [
            SupportTicket(
                id=ticket.id,
                telegram_id=ticket.telegram_id,
                status=ticket.status,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                last_message=(
                    self._support_messages[ticket.id][-1].body
                    if self._support_messages[ticket.id]
                    else ""
                ),
            )
            for ticket in self._support_tickets.values()
            if ticket.status == "open"
        ]
        tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
        return tickets[:limit]

    async def list_support_tickets_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 20,
    ) -> Sequence[SupportTicket]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество обращений должно быть от 1 до 100")
        tickets = [
            SupportTicket(
                id=ticket.id,
                telegram_id=ticket.telegram_id,
                status=ticket.status,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                last_message=(
                    self._support_messages[ticket.id][-1].body
                    if self._support_messages[ticket.id]
                    else ""
                ),
            )
            for ticket in self._support_tickets.values()
            if ticket.telegram_id == telegram_id
        ]
        tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
        return tickets[:limit]

    async def close_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
    ) -> Optional[int]:
        _ = admin_telegram_id
        ticket = self._support_tickets.get(ticket_id)
        if ticket is None or ticket.status != "open":
            return None
        self._support_tickets[ticket_id] = SupportTicket(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status="closed",
            created_at=ticket.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        return ticket.telegram_id

    async def create_lesson_request(
        self,
        telegram_id: int,
        kind: str,
        details: str,
    ) -> LessonRequest:
        if telegram_id not in self._profiles:
            raise LookupError("Сначала создайте профиль командой /start")
        if kind not in {"booking", "purchase"}:
            raise ValueError("Неизвестный тип заявки")
        request = LessonRequest(
            id=self._next_request_id,
            telegram_id=telegram_id,
            kind=kind,
            details=details,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        self._requests[request.id] = request
        self._next_request_id += 1
        return request

    async def list_pending_requests(self, limit: int = 20) -> Sequence[LessonRequest]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество заявок должно быть от 1 до 100")
        requests = [
            request
            for request in self._requests.values()
            if request.status == "pending"
        ]
        requests.sort(key=lambda request: request.created_at, reverse=True)
        return requests[:limit]

    async def complete_request(self, request_id: int) -> bool:
        request = self._requests.get(request_id)
        if request is None or request.status != "pending":
            return False
        self._requests[request_id] = LessonRequest(
            id=request.id,
            telegram_id=request.telegram_id,
            kind=request.kind,
            details=request.details,
            status="completed",
            created_at=request.created_at,
        )
        if request.kind == "booking":
            profile = self._get_profile(request.telegram_id)
            if profile.lesson_credits > 0:
                self._profiles[request.telegram_id] = UserProfile(
                    telegram_id=profile.telegram_id,
                    phone=profile.phone,
                    user_name=profile.user_name,
                    registered_at=profile.registered_at,
                    is_admin=profile.is_admin,
                    lesson_credits=profile.lesson_credits - 1,
                )
                legacy_credits = profile.lesson_credits - sum(
                    max(0, self._payment_credit_balance(payment.id))
                    for payment in self._payments.values()
                    if payment.telegram_id == request.telegram_id
                    and payment.status == "succeeded"
                )
                source_payment_id = None
                if legacy_credits <= 0:
                    for payment in self._payments.values():
                        if (
                            payment.telegram_id == request.telegram_id
                            and payment.status == "succeeded"
                            and self._payment_credit_balance(payment.id) > 0
                        ):
                            source_payment_id = payment.id
                            break
                self._append_ledger(
                    request.telegram_id,
                    -1,
                    "lesson_use",
                    source_payment_id,
                    reference_key="request:{}".format(request_id),
                )
        return True

    def _get_profile(self, telegram_id: int) -> UserProfile:
        profile = self._profiles.get(telegram_id)
        if profile is None:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )
        return profile

    def _payment_credit_balance(self, payment_id: int) -> int:
        return sum(
            row.delta for row in self._credit_ledger if row.payment_id == payment_id
        )

    async def create_web_user(
        self,
        email: str,
        password_hash: str,
        display_name: str,
    ) -> WebUserRecord:
        normalized_email = email.lower()
        if any(
            user.email is not None and user.email.lower() == normalized_email
            for user in self._web_users.values()
        ):
            raise EmailAlreadyRegisteredError("Этот email уже зарегистрирован")
        user = WebUserRecord(
            id=self._next_web_user_id,
            email=email,
            password_hash=password_hash,
            telegram_id=None,
            display_name=display_name,
            created_at=datetime.now(timezone.utc),
        )
        self._web_users[user.id] = user
        self._next_web_user_id += 1
        return user

    async def get_or_create_web_user_from_telegram(
        self,
        telegram_id: int,
        display_name: str,
    ) -> WebUserRecord:
        existing = await self.get_web_user_by_telegram_id(telegram_id)
        if existing is not None:
            return existing
        user = WebUserRecord(
            id=self._next_web_user_id,
            email=None,
            password_hash=None,
            telegram_id=telegram_id,
            display_name=display_name,
            created_at=datetime.now(timezone.utc),
        )
        self._web_users[user.id] = user
        self._next_web_user_id += 1
        return user

    def _with_profile_name(
        self, user: Optional[WebUserRecord]
    ) -> Optional[WebUserRecord]:
        """Как _WEB_USER_SELECT у PostgreSQL: имя — из профиля бота, право
        администратора — с веб-аккаунта или из профиля бота."""
        if user is None or user.telegram_id not in self._profiles:
            return user
        profile = self._profiles[user.telegram_id]
        return replace(
            user,
            display_name=profile.user_name,
            is_admin=user.is_admin or profile.is_admin,
        )

    async def get_web_user_by_id(self, user_id: int) -> Optional[WebUserRecord]:
        return self._with_profile_name(self._web_users.get(user_id))

    async def create_web_session(
        self,
        user_id: int,
        token: str,
        expires_at: datetime,
    ) -> None:
        now = datetime.now(timezone.utc)
        for existing_hash, (existing_user_id, existing_expiry) in list(
            self._web_sessions.items()
        ):
            if existing_user_id == user_id and existing_expiry <= now:
                del self._web_sessions[existing_hash]
        self._web_sessions[hash_session_token(token)] = (user_id, expires_at)

    async def get_web_session_user_id(self, token: str) -> Optional[int]:
        entry = self._web_sessions.get(hash_session_token(token))
        if entry is None:
            return None
        user_id, expires_at = entry
        if expires_at <= datetime.now(timezone.utc):
            return None
        return user_id

    async def delete_web_session(self, token: str) -> None:
        self._web_sessions.pop(hash_session_token(token), None)

    async def get_web_user_by_email(self, email: str) -> Optional[WebUserRecord]:
        normalized_email = email.lower()
        for user in self._web_users.values():
            if user.email is not None and user.email.lower() == normalized_email:
                return self._with_profile_name(user)
        return None

    async def get_web_user_by_telegram_id(
        self,
        telegram_id: int,
    ) -> Optional[WebUserRecord]:
        for user in self._web_users.values():
            if user.telegram_id == telegram_id:
                return self._with_profile_name(user)
        return None

    async def set_web_user_telegram_id(
        self,
        user_id: int,
        telegram_id: Optional[int],
    ) -> bool:
        user = self._web_users.get(user_id)
        if user is None:
            return False
        if telegram_id is not None and any(
            other.id != user_id and other.telegram_id == telegram_id
            for other in self._web_users.values()
        ):
            raise TelegramAlreadyLinkedError(
                "Этот Telegram уже привязан к другому аккаунту"
            )
        self._web_users[user_id] = replace(user, telegram_id=telegram_id)
        return True

    async def set_web_user_credentials(
        self,
        user_id: int,
        email: str,
        password_hash: str,
    ) -> bool:
        user = self._web_users.get(user_id)
        if user is None or user.email is not None:
            return False
        if any(
            other.email is not None and other.email.lower() == email.lower()
            for other in self._web_users.values()
        ):
            raise EmailAlreadyRegisteredError("Этот email уже зарегистрирован")
        self._web_users[user_id] = replace(
            user, email=email, password_hash=password_hash
        )
        return True

    async def set_web_user_password(self, user_id: int, password_hash: str) -> bool:
        user = self._web_users.get(user_id)
        if user is None or user.email is None:
            return False
        self._web_users[user_id] = replace(user, password_hash=password_hash)
        return True

    async def set_web_user_admin(self, user_id: int, is_admin: bool) -> bool:
        user = self._web_users.get(user_id)
        if user is None:
            return False
        self._web_users[user_id] = replace(user, is_admin=is_admin)
        return True
