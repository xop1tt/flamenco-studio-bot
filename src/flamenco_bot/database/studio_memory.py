"""Временное хранилище: те же операции, что в ``studio_postgres.py``.

Используется только без PostgreSQL (development и unit-тесты). Правила
(источник списания, остатки абонементов, окно отмены, идемпотентность
возвратов) считаются теми же функциями, что и для PostgreSQL. Модуль
импортируется из ``repository.py`` после объявления общих типов.
"""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, NamedTuple, Optional, Sequence, Tuple

from .repository import (
    ClassSlot,
    SupportTicket,
    TelegramAlreadyLinkedError,
    WebUserRecord,
)
from .studio_models import (
    LOW_BALANCE_THRESHOLD,
    NOTIFICATION_KINDS,
    AuditEvent,
    CreditSource,
    LedgerEntry,
    NotificationSettings,
    PackageGrant,
    PackageGrantNotFoundError,
    PackageGrantResult,
    PackageRevokeResult,
    PackageSummary,
    SlotCancellation,
    SlotEvent,
    SlotNotFoundError,
    SlotParticipant,
    SlotRefund,
    SlotReschedule,
    SlotStateError,
    SupportThreadMessage,
    SupportTicketStateError,
    SupportTicketThread,
    TelegramConnectError,
    TelegramConnectRequest,
    UserNotification,
    effective_remaining,
    low_balance_dedupe_key,
    normalize_reason,
    pick_credit_source_index,
    reminder_dedupe_key,
)


CONNECT_CONSUME_WINDOW = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryLedgerRow(NamedTuple):
    """Строка ledger во временном хранилище (первые 4 поля — как раньше)."""

    telegram_id: int
    delta: int
    entry_type: str
    payment_id: Optional[int]
    id: int = 0
    created_at: Optional[datetime] = None
    grant_id: Optional[int] = None
    booking_id: Optional[int] = None
    actor_telegram_id: Optional[int] = None
    reason: Optional[str] = None
    reference_key: Optional[str] = None


class InMemoryStudioMixin:
    # Состояние создаёт InMemoryRepository.__init__ (см. _init_studio_state).
    _profiles: Dict[int, Any]
    _payments: Dict[int, Any]
    _payment_created_at: Dict[int, datetime]
    _credit_ledger: list
    _class_slots: Dict[int, ClassSlot]
    _class_bookings: Dict[Tuple[int, int], Any]
    _support_tickets: Dict[int, SupportTicket]
    _support_messages: Dict[int, list]
    _web_users: Dict[int, WebUserRecord]
    _web_sessions: Dict[str, Tuple[int, datetime]]

    def _init_studio_state(self) -> None:
        self._next_ledger_id = 1
        self._slot_events: list[SlotEvent] = []
        self._next_slot_event_id = 1
        self._grants: Dict[int, PackageGrant] = {}
        self._grant_keys: Dict[uuid.UUID, int] = {}
        self._next_grant_id = 1
        self._notifications: Dict[int, dict] = {}
        self._notification_keys: set[str] = set()
        self._next_notification_id = 1
        self._notification_settings: Dict[int, NotificationSettings] = {}
        self._connect_requests: Dict[int, dict] = {}
        self._next_connect_id = 1

    # ---------- ledger и баланс ----------

    def _append_ledger(
        self,
        telegram_id: int,
        delta: int,
        entry_type: str,
        payment_id: Optional[int] = None,
        *,
        grant_id: Optional[int] = None,
        booking_id: Optional[int] = None,
        actor_telegram_id: Optional[int] = None,
        reason: Optional[str] = None,
        reference_key: Optional[str] = None,
    ) -> Optional[int]:
        """Пишет строку ledger; ``None`` — строка с таким ключом уже есть."""
        if reference_key is not None and any(
            row.reference_key == reference_key for row in self._credit_ledger
        ):
            return None
        row = MemoryLedgerRow(
            telegram_id=telegram_id,
            delta=delta,
            entry_type=entry_type,
            payment_id=payment_id,
            id=self._next_ledger_id,
            created_at=_now(),
            grant_id=grant_id,
            booking_id=booking_id,
            actor_telegram_id=actor_telegram_id,
            reason=reason,
            reference_key=reference_key,
        )
        self._next_ledger_id += 1
        self._credit_ledger.append(row)
        return row.id

    def _set_credits(self, telegram_id: int, credits: int) -> None:
        profile = self._profiles[telegram_id]
        self._profiles[telegram_id] = replace(profile, lesson_credits=credits)

    def _source_sum(self, kind: str, source_id: int) -> int:
        field_name = "payment_id" if kind == "payment" else "grant_id"
        return sum(
            row.delta
            for row in self._credit_ledger
            if getattr(row, field_name, None) == source_id
        )

    def _active_sources(self, telegram_id: int) -> list:
        sources = []
        for payment in self._payments.values():
            if payment.telegram_id == telegram_id and payment.status == "succeeded":
                remaining = self._source_sum("payment", payment.id)
                if remaining > 0:
                    sources.append(
                        (
                            self._payment_created_at.get(payment.id, _now()),
                            "payment",
                            payment.id,
                            payment.package_title,
                            payment.lessons,
                            remaining,
                        )
                    )
        for grant in self._grants.values():
            if grant.telegram_id == telegram_id and grant.status == "active":
                remaining = self._source_sum("grant", grant.id)
                if remaining > 0:
                    sources.append(
                        (
                            grant.created_at,
                            "grant",
                            grant.id,
                            grant.title,
                            grant.lessons,
                            remaining,
                        )
                    )
        sources.sort(key=lambda item: (item[0], item[1], item[2]))
        return sources

    def _memory_pick_source(self, telegram_id: int) -> Optional[CreditSource]:
        balance = self._profiles[telegram_id].lesson_credits
        sources = self._active_sources(telegram_id)
        raw = [item[5] for item in sources]
        index = pick_credit_source_index(balance, raw)
        if index is None:
            return None
        effective, _ = effective_remaining(balance, raw)
        _, kind, source_id, title, lessons, _ = sources[index]
        return CreditSource(kind, source_id, title, lessons, effective[index])

    def _memory_enqueue_low_balance(self, telegram_id: int, balance: int) -> None:
        if balance > LOW_BALANCE_THRESHOLD:
            return
        if not self._settings(telegram_id).low_balance:
            return
        marker = max(
            (
                row.id
                for row in self._credit_ledger
                if row.telegram_id == telegram_id
                and row.delta > 0
                and row.entry_type
                in {"purchase", "package_grant", "admin_adjustment", "refund_release"}
            ),
            default=0,
        )
        self._memory_enqueue(
            telegram_id,
            "low_balance",
            {"balance": balance},
            low_balance_dedupe_key(telegram_id, marker),
        )

    # ---------- слоты ----------

    def _memory_slot(self, slot_id: int) -> Optional[ClassSlot]:
        slot = self._class_slots.get(slot_id)
        return self._slot_with_count(slot) if slot is not None else None

    def _record_slot_event(self, slot_id: int, event_type: str, **values: Any) -> int:
        event = SlotEvent(
            id=self._next_slot_event_id,
            slot_id=slot_id,
            event_type=event_type,
            actor_telegram_id=values.get("actor_telegram_id"),
            old_starts_at=values.get("old_starts_at"),
            new_starts_at=values.get("new_starts_at"),
            old_capacity=values.get("old_capacity"),
            new_capacity=values.get("new_capacity"),
            reason=values.get("reason"),
            created_at=_now(),
            class_key=self._class_slots[slot_id].class_key,
        )
        self._next_slot_event_id += 1
        self._slot_events.append(event)
        return event.id

    async def get_class_slot(self, slot_id: int) -> Optional[ClassSlot]:
        return self._memory_slot(slot_id)

    async def list_slot_participants(
        self,
        slot_id: int,
        include_cancelled: bool = False,
    ) -> Sequence[SlotParticipant]:
        participants = []
        for (booking_slot_id, telegram_id), booking in self._class_bookings.items():
            if booking_slot_id != slot_id:
                continue
            if booking.status != "confirmed" and not include_cancelled:
                continue
            profile = self._profiles.get(telegram_id)
            participants.append(
                SlotParticipant(
                    booking_id=booking.id,
                    telegram_id=telegram_id,
                    user_name=profile.user_name if profile else "Участник",
                    phone=profile.phone if profile else None,
                    booked_at=booking.booked_at or booking.updated_at,
                    status=booking.status,
                )
            )
        participants.sort(key=lambda item: (item.status != "confirmed", item.booked_at))
        return participants

    async def list_slot_events(
        self,
        slot_id: Optional[int] = None,
        limit: int = 30,
    ) -> Sequence[SlotEvent]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество событий должно быть от 1 до 100")
        events = [
            event
            for event in self._slot_events
            if slot_id is None or event.slot_id == slot_id
        ]
        return list(reversed(events))[:limit]

    async def reschedule_class_slot(
        self,
        slot_id: int,
        new_starts_at: datetime,
        admin_telegram_id: int,
        reason: Optional[str] = None,
    ) -> SlotReschedule:
        if new_starts_at.tzinfo is None or new_starts_at.utcoffset() is None:
            raise ValueError("Время занятия должно содержать часовой пояс")
        if new_starts_at <= _now():
            raise ValueError("Новое время занятия должно быть в будущем")
        normalized_reason = normalize_reason(reason, required=False)
        slot = self._class_slots.get(slot_id)
        if slot is None:
            raise SlotNotFoundError("Занятие не найдено")
        if slot.status == "cancelled":
            raise SlotStateError("Занятие отменено — перенести его нельзя")
        if slot.starts_at <= _now():
            raise SlotStateError("Занятие уже началось — перенести его нельзя")
        if slot.starts_at == new_starts_at:
            raise ValueError("Новое время совпадает с текущим")
        old_starts_at = slot.starts_at
        self._class_slots[slot_id] = replace(
            slot, starts_at=new_starts_at, rescheduled_at=_now()
        )
        event_id = self._record_slot_event(
            slot_id,
            "rescheduled",
            actor_telegram_id=admin_telegram_id,
            old_starts_at=old_starts_at,
            new_starts_at=new_starts_at,
            reason=normalized_reason,
        )
        participants = sorted(
            (telegram_id, booking.id)
            for (booking_slot_id, telegram_id), booking in self._class_bookings.items()
            if booking_slot_id == slot_id and booking.status == "confirmed"
        )
        for telegram_id, booking_id in participants:
            self._memory_enqueue(
                telegram_id,
                "slot_rescheduled",
                {
                    "slot_id": slot_id,
                    "class_key": slot.class_key,
                    "old_starts_at": old_starts_at.isoformat(),
                    "new_starts_at": new_starts_at.isoformat(),
                    "reason": normalized_reason,
                },
                "slot_rescheduled:{}:{}".format(event_id, booking_id),
            )
        return SlotReschedule(
            slot=self._memory_slot(slot_id),
            old_starts_at=old_starts_at,
            new_starts_at=new_starts_at,
            participants=tuple(telegram_id for telegram_id, _ in participants),
        )

    async def cancel_class_slot(
        self,
        slot_id: int,
        admin_telegram_id: int,
        reason: Optional[str] = None,
    ) -> SlotCancellation:
        normalized_reason = normalize_reason(reason, required=False)
        slot = self._class_slots.get(slot_id)
        if slot is None:
            raise SlotNotFoundError("Занятие не найдено")
        if slot.status == "cancelled":
            return SlotCancellation(
                slot=self._memory_slot(slot_id), already_cancelled=True
            )
        if slot.starts_at <= _now():
            raise SlotStateError("Занятие уже началось — отменить его нельзя")
        cancelled_at = _now()
        self._class_slots[slot_id] = replace(
            slot,
            status="cancelled",
            cancelled_at=cancelled_at,
            cancel_reason=normalized_reason,
        )
        self._record_slot_event(
            slot_id,
            "cancelled",
            actor_telegram_id=admin_telegram_id,
            reason=normalized_reason,
        )
        refunds = []
        affected = sorted(
            (telegram_id, booking)
            for (booking_slot_id, telegram_id), booking in self._class_bookings.items()
            if booking_slot_id == slot_id and booking.status == "confirmed"
        )
        for telegram_id, booking in affected:
            self._class_bookings[(slot_id, telegram_id)] = replace(
                booking, status="cancelled", updated_at=cancelled_at
            )
            payment_id, grant_id = self._booking_source(booking.id)
            ledger_id = self._append_ledger(
                telegram_id,
                1,
                "slot_cancellation",
                payment_id,
                grant_id=grant_id,
                booking_id=booking.id,
                actor_telegram_id=admin_telegram_id,
                reason=normalized_reason,
                reference_key="slot_cancellation:{}:{}".format(slot_id, booking.id),
            )
            balance = self._profiles[telegram_id].lesson_credits
            if ledger_id is not None:
                balance += 1
                self._set_credits(telegram_id, balance)
            self._memory_enqueue(
                telegram_id,
                "slot_cancelled",
                {
                    "slot_id": slot_id,
                    "class_key": slot.class_key,
                    "starts_at": slot.starts_at.isoformat(),
                    "reason": normalized_reason,
                    "refunded": True,
                    "balance": balance,
                },
                "slot_cancelled:{}:{}".format(slot_id, booking.id),
            )
            refunds.append(SlotRefund(booking.id, telegram_id, balance))
        return SlotCancellation(
            slot=self._memory_slot(slot_id),
            already_cancelled=False,
            refunds=tuple(refunds),
        )

    async def reopen_class_slot(
        self,
        slot_id: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        slot = self._class_slots.get(slot_id)
        if slot is None or slot.status != "closed" or slot.starts_at <= _now():
            return False
        self._class_slots[slot_id] = replace(slot, status="open")
        self._record_slot_event(
            slot_id, "reopened", actor_telegram_id=admin_telegram_id
        )
        return True

    def _booking_source(self, booking_id: int) -> Tuple[Optional[int], Optional[int]]:
        for row in reversed(self._credit_ledger):
            if row.booking_id == booking_id and row.entry_type == "lesson_use":
                return row.payment_id, row.grant_id
        return None, None

    # ---------- абонементы ----------

    async def get_package_summary(self, telegram_id: int) -> PackageSummary:
        from .studio_postgres import build_package_summary

        profile = self._profiles.get(telegram_id)
        if profile is None:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )
        records = []
        for payment in self._payments.values():
            if payment.telegram_id != telegram_id or payment.status not in {
                "succeeded",
                "refund_pending",
                "refunded",
            }:
                continue
            records.append(
                {
                    "kind": "payment",
                    "id": payment.id,
                    "package_key": payment.package_key,
                    "title": payment.package_title,
                    "lessons": payment.lessons,
                    "source_status": payment.status,
                    "acquired_at": self._payment_created_at.get(payment.id, _now()),
                    "amount_minor": payment.amount_minor,
                    "reason": None,
                    "raw_remaining": self._source_sum("payment", payment.id),
                }
            )
        for grant in self._grants.values():
            if grant.telegram_id != telegram_id:
                continue
            records.append(
                {
                    "kind": "grant",
                    "id": grant.id,
                    "package_key": grant.package_key,
                    "title": grant.title,
                    "lessons": grant.lessons,
                    "source_status": grant.status,
                    "acquired_at": grant.created_at,
                    "amount_minor": None,
                    "reason": grant.reason,
                    "raw_remaining": self._source_sum("grant", grant.id),
                }
            )
        records.sort(key=lambda item: (item["acquired_at"], item["kind"], item["id"]))
        return build_package_summary(profile.lesson_credits, records)

    async def get_package_grant(self, grant_id: int) -> Optional[PackageGrant]:
        return self._grants.get(grant_id)

    def _memory_require_admin(self, actor_telegram_id: int) -> None:
        actor = self._profiles.get(actor_telegram_id)
        if actor is None or not actor.is_admin:
            raise PermissionError("Действие доступно только администратору")

    async def grant_lesson_package(
        self,
        telegram_id: int,
        package_key: str,
        title: str,
        lessons: int,
        reason: str,
        admin_telegram_id: int,
        idempotence_key: uuid.UUID,
    ) -> PackageGrantResult:
        normalized_reason = normalize_reason(reason, required=True)
        normalized_title = title.strip()
        if not 1 <= len(normalized_title) <= 100:
            raise ValueError(
                "Название абонемента должно содержать от 1 до 100 символов"
            )
        if not 1 <= lessons <= 100:
            raise ValueError("Количество занятий должно быть от 1 до 100")
        self._memory_require_admin(admin_telegram_id)
        if telegram_id not in self._profiles:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )
        existing_id = self._grant_keys.get(idempotence_key)
        if existing_id is not None:
            existing = self._grants[existing_id]
            if existing.telegram_id != telegram_id or existing.lessons != lessons:
                raise ValueError(
                    "Ключ идемпотентности уже использован для другой выдачи"
                )
            return PackageGrantResult(
                existing, None, self._profiles[telegram_id].lesson_credits, False
            )
        grant = PackageGrant(
            id=self._next_grant_id,
            telegram_id=telegram_id,
            package_key=package_key,
            title=normalized_title,
            lessons=lessons,
            status="active",
            granted_by=admin_telegram_id,
            reason=normalized_reason,
            created_at=_now(),
        )
        self._next_grant_id += 1
        self._grants[grant.id] = grant
        self._grant_keys[idempotence_key] = grant.id
        ledger_id = self._append_ledger(
            telegram_id,
            lessons,
            "package_grant",
            grant_id=grant.id,
            actor_telegram_id=admin_telegram_id,
            reason=normalized_reason,
            reference_key="package-grant:{}".format(grant.id),
        )
        balance = self._profiles[telegram_id].lesson_credits + lessons
        self._set_credits(telegram_id, balance)
        self._memory_enqueue(
            telegram_id,
            "package_granted",
            {
                "grant_id": grant.id,
                "title": normalized_title,
                "lessons": lessons,
                "balance": balance,
            },
            "package_granted:{}".format(grant.id),
        )
        return PackageGrantResult(grant, ledger_id, balance, True)

    async def revoke_lesson_package_grant(
        self,
        grant_id: int,
        reason: str,
        admin_telegram_id: int,
    ) -> PackageRevokeResult:
        normalized_reason = normalize_reason(reason, required=True)
        self._memory_require_admin(admin_telegram_id)
        grant = self._grants.get(grant_id)
        if grant is None:
            raise PackageGrantNotFoundError("Выданный абонемент не найден")
        balance = self._profiles[grant.telegram_id].lesson_credits
        if grant.status == "revoked":
            return PackageRevokeResult(grant, 0, balance, False)
        sources = self._active_sources(grant.telegram_id)
        effective, _ = effective_remaining(balance, [item[5] for item in sources])
        revoked_lessons = next(
            (
                effective[index]
                for index, item in enumerate(sources)
                if item[1] == "grant" and item[2] == grant_id
            ),
            0,
        )
        grant = replace(grant, status="revoked")
        self._grants[grant_id] = grant
        if revoked_lessons > 0:
            self._append_ledger(
                grant.telegram_id,
                -revoked_lessons,
                "package_revoke",
                grant_id=grant_id,
                actor_telegram_id=admin_telegram_id,
                reason=normalized_reason,
                reference_key="package-revoke:{}".format(grant_id),
            )
            balance -= revoked_lessons
            self._set_credits(grant.telegram_id, balance)
        self._memory_enqueue(
            grant.telegram_id,
            "package_revoked",
            {
                "grant_id": grant_id,
                "title": grant.title,
                "revoked_lessons": revoked_lessons,
                "balance": balance,
                "reason": normalized_reason,
            },
            "package_revoked:{}".format(grant_id),
        )
        return PackageRevokeResult(grant, revoked_lessons, balance, True)

    # ---------- история и аудит ----------

    def _ledger_entry(self, row: MemoryLedgerRow) -> LedgerEntry:
        title = None
        if row.payment_id is not None and row.payment_id in self._payments:
            title = self._payments[row.payment_id].package_title
        elif row.grant_id is not None and row.grant_id in self._grants:
            title = self._grants[row.grant_id].title
        class_key = starts_at = None
        if row.booking_id is not None:
            for (slot_id, _), booking in self._class_bookings.items():
                if booking.id == row.booking_id:
                    slot = self._class_slots[slot_id]
                    class_key, starts_at = slot.class_key, slot.starts_at
                    break
        profile = self._profiles.get(row.telegram_id)
        return LedgerEntry(
            id=row.id,
            telegram_id=row.telegram_id,
            entry_type=row.entry_type,
            delta=row.delta,
            created_at=row.created_at or _now(),
            reason=row.reason,
            actor_telegram_id=row.actor_telegram_id,
            payment_id=row.payment_id,
            grant_id=row.grant_id,
            booking_id=row.booking_id,
            package_title=title,
            class_key=class_key,
            starts_at=starts_at,
            user_name=profile.user_name if profile else None,
        )

    async def list_credit_history(
        self,
        telegram_id: Optional[int],
        limit: int = 20,
        before_id: Optional[int] = None,
    ) -> Sequence[LedgerEntry]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество операций должно быть от 1 до 100")
        rows = [
            row
            for row in reversed(self._credit_ledger)
            if (telegram_id is None or row.telegram_id == telegram_id)
            and (before_id is None or row.id < before_id)
        ]
        return [self._ledger_entry(row) for row in rows[:limit]]

    async def list_audit_events(self, limit: int = 30) -> Sequence[AuditEvent]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество событий должно быть от 1 до 100")
        events = [
            AuditEvent(
                source="ledger",
                action=row.entry_type,
                created_at=row.created_at or _now(),
                actor_telegram_id=row.actor_telegram_id,
                target_telegram_id=row.telegram_id,
                payment_id=row.payment_id,
                delta=row.delta,
                reason=row.reason,
            )
            for row in self._credit_ledger
            if row.actor_telegram_id is not None
            and row.entry_type != "slot_cancellation"
        ]
        events.extend(
            AuditEvent(
                source="slot",
                action=event.event_type,
                created_at=event.created_at,
                actor_telegram_id=event.actor_telegram_id,
                slot_id=event.slot_id,
                reason=event.reason,
            )
            for event in self._slot_events
        )
        events.sort(key=lambda event: event.created_at, reverse=True)
        return events[:limit]

    # ---------- уведомления ----------

    def _settings(self, telegram_id: int) -> NotificationSettings:
        return self._notification_settings.get(telegram_id, NotificationSettings())

    def _memory_enqueue(
        self,
        telegram_id: int,
        kind: str,
        payload: dict,
        dedupe_key: str,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        if kind not in NOTIFICATION_KINDS:
            raise ValueError("Неизвестный тип уведомления")
        if dedupe_key in self._notification_keys:
            return False
        self._notification_keys.add(dedupe_key)
        notification_id = self._next_notification_id
        self._next_notification_id += 1
        self._notifications[notification_id] = {
            "id": notification_id,
            "telegram_id": telegram_id,
            "kind": kind,
            "payload": dict(payload),
            "created_at": _now(),
            "delivery_status": "pending",
            "attempts": 0,
            "read_at": None,
            "expires_at": expires_at,
            "sent_at": None,
            "next_attempt_at": _now(),
            "last_error": None,
        }
        return True

    @staticmethod
    def _notification(data: dict) -> UserNotification:
        return UserNotification(
            id=data["id"],
            telegram_id=data["telegram_id"],
            kind=data["kind"],
            payload=dict(data["payload"]),
            created_at=data["created_at"],
            delivery_status=data["delivery_status"],
            attempts=data["attempts"],
            read_at=data["read_at"],
            expires_at=data["expires_at"],
            sent_at=data["sent_at"],
        )

    async def enqueue_notification(
        self,
        telegram_id: int,
        kind: str,
        payload: dict,
        dedupe_key: str,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        return self._memory_enqueue(telegram_id, kind, payload, dedupe_key, expires_at)

    async def claim_due_notifications(
        self,
        limit: int = 20,
        lease: timedelta = timedelta(minutes=2),
    ) -> Sequence[UserNotification]:
        now = _now()
        claimed = []
        for data in sorted(self._notifications.values(), key=lambda item: item["id"]):
            if data["delivery_status"] not in {"pending", "sending"}:
                continue
            if data["expires_at"] is not None and data["expires_at"] <= now:
                data["delivery_status"] = "skipped"
                data["last_error"] = "expired"
                continue
            if data["next_attempt_at"] > now or len(claimed) >= limit:
                continue
            data["delivery_status"] = "sending"
            data["attempts"] += 1
            data["next_attempt_at"] = now + lease
            claimed.append(self._notification(data))
        return claimed

    async def mark_notification_sent(self, notification_id: int) -> None:
        data = self._notifications[notification_id]
        data.update(delivery_status="sent", sent_at=_now(), last_error=None)

    async def mark_notification_retry(
        self,
        notification_id: int,
        error: str,
        retry_at: datetime,
    ) -> None:
        data = self._notifications[notification_id]
        if data["delivery_status"] == "sending":
            data.update(
                delivery_status="pending", next_attempt_at=retry_at, last_error=error
            )

    async def mark_notification_finished(
        self,
        notification_id: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        if status not in {"failed", "skipped"}:
            raise ValueError("Недопустимый итоговый статус уведомления")
        self._notifications[notification_id].update(
            delivery_status=status, last_error=error
        )

    async def list_notifications(
        self,
        telegram_id: int,
        limit: int = 20,
        unread_only: bool = False,
        before_id: Optional[int] = None,
    ) -> Sequence[UserNotification]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество уведомлений должно быть от 1 до 100")
        items = [
            self._notification(data)
            for data in sorted(
                self._notifications.values(), key=lambda item: item["id"], reverse=True
            )
            if data["telegram_id"] == telegram_id
            and (not unread_only or data["read_at"] is None)
            and (before_id is None or data["id"] < before_id)
        ]
        return items[:limit]

    async def count_unread_notifications(self, telegram_id: int) -> int:
        return sum(
            1
            for data in self._notifications.values()
            if data["telegram_id"] == telegram_id and data["read_at"] is None
        )

    async def mark_notifications_read(
        self,
        telegram_id: int,
        notification_ids: Optional[Sequence[int]] = None,
    ) -> int:
        wanted = set(notification_ids) if notification_ids is not None else None
        updated = 0
        for data in self._notifications.values():
            if (
                data["telegram_id"] == telegram_id
                and data["read_at"] is None
                and (wanted is None or data["id"] in wanted)
            ):
                data["read_at"] = _now()
                updated += 1
        return updated

    async def get_notification_settings(self, telegram_id: int) -> NotificationSettings:
        if telegram_id not in self._profiles:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )
        return self._settings(telegram_id)

    async def update_notification_settings(
        self,
        telegram_id: int,
        reminders: Optional[bool] = None,
        low_balance: Optional[bool] = None,
    ) -> NotificationSettings:
        current = await self.get_notification_settings(telegram_id)
        updated = NotificationSettings(
            reminders=current.reminders if reminders is None else reminders,
            low_balance=current.low_balance if low_balance is None else low_balance,
        )
        self._notification_settings[telegram_id] = updated
        return updated

    async def enqueue_due_reminders(self, lead: timedelta) -> int:
        now = _now()
        created = 0
        for (slot_id, telegram_id), booking in list(self._class_bookings.items()):
            slot = self._class_slots[slot_id]
            booked_at = booking.booked_at or booking.updated_at
            if (
                booking.status != "confirmed"
                or slot.status == "cancelled"
                or not now < slot.starts_at <= now + lead
                or booked_at >= slot.starts_at - lead
                or not self._settings(telegram_id).reminders
            ):
                continue
            created += self._memory_enqueue(
                telegram_id,
                "lesson_reminder",
                {
                    "slot_id": slot_id,
                    "booking_id": booking.id,
                    "class_key": slot.class_key,
                    "starts_at": slot.starts_at.isoformat(),
                },
                reminder_dedupe_key(booking.id, slot.starts_at),
                expires_at=slot.starts_at,
            )
        return created

    async def is_reminder_current(self, booking_id: int, starts_at: datetime) -> bool:
        for (slot_id, _), booking in self._class_bookings.items():
            if booking.id != booking_id:
                continue
            slot = self._class_slots[slot_id]
            return (
                booking.status == "confirmed"
                and slot.status != "cancelled"
                and slot.starts_at == starts_at
                and slot.starts_at > _now()
            )
        return False

    # ---------- вход на сайт через бота ----------

    def _connect_request(self, data: dict) -> TelegramConnectRequest:
        user = self._web_users.get(data["web_user_id"]) if data["web_user_id"] else None
        return TelegramConnectRequest(
            id=data["id"],
            purpose=data["purpose"],
            status=data["status"],
            expires_at=data["expires_at"],
            web_user_id=data["web_user_id"],
            telegram_id=data["telegram_id"],
            web_user_email=user.email if user else None,
        )

    def _find_connect(self, field_name: str, value: str) -> Optional[dict]:
        from .studio_postgres import secret_hash

        hashed = secret_hash(value)
        return next(
            (
                data
                for data in self._connect_requests.values()
                if data[field_name] == hashed
            ),
            None,
        )

    async def create_telegram_connect_request(
        self,
        token: str,
        browser_secret: str,
        purpose: str,
        web_user_id: Optional[int],
        expires_at: datetime,
    ) -> int:
        from .studio_postgres import secret_hash

        if purpose not in {"login", "link"} or (purpose == "link") != (
            web_user_id is not None
        ):
            raise ValueError("Некорректный запрос входа через Telegram")
        request_id = self._next_connect_id
        self._next_connect_id += 1
        self._connect_requests[request_id] = {
            "id": request_id,
            "token_hash": secret_hash(token),
            "browser_secret_hash": secret_hash(browser_secret),
            "purpose": purpose,
            "web_user_id": web_user_id,
            "telegram_id": None,
            "status": "pending",
            "expires_at": expires_at,
            "confirmed_at": None,
        }
        return request_id

    async def get_telegram_connect_request(
        self, token: str
    ) -> Optional[TelegramConnectRequest]:
        data = self._find_connect("token_hash", token)
        return self._connect_request(data) if data else None

    async def confirm_telegram_connect_request(
        self, token: str, telegram_id: int
    ) -> TelegramConnectRequest:
        data = self._find_connect("token_hash", token)
        if data is None or data["status"] != "pending" or data["expires_at"] <= _now():
            raise TelegramConnectError("Ссылка для входа недействительна или устарела")
        if data["purpose"] == "link":
            await self.link_telegram_to_web_user(data["web_user_id"], telegram_id)
        data.update(status="confirmed", telegram_id=telegram_id, confirmed_at=_now())
        return self._connect_request(data)

    async def reject_telegram_connect_request(self, token: str) -> bool:
        data = self._find_connect("token_hash", token)
        if data is None or data["status"] != "pending":
            return False
        data["status"] = "rejected"
        return True

    async def consume_telegram_connect_request(
        self, browser_secret: str
    ) -> Tuple[Optional[TelegramConnectRequest], bool]:
        data = self._find_connect("browser_secret_hash", browser_secret)
        if data is None:
            return None, False
        consumed_now = (
            data["status"] == "confirmed"
            and data["confirmed_at"] + CONNECT_CONSUME_WINDOW > _now()
        )
        if consumed_now:
            data["status"] = "consumed"
        return self._connect_request(data), consumed_now

    async def link_telegram_to_web_user(self, user_id: int, telegram_id: int) -> None:
        holder = next(
            (
                user
                for user in self._web_users.values()
                if user.telegram_id == telegram_id
            ),
            None,
        )
        if holder is not None and holder.id != user_id:
            if holder.email is not None:
                raise TelegramAlreadyLinkedError(
                    "Этот Telegram уже привязан к другому аккаунту"
                )
            del self._web_users[holder.id]
            for token_hash, (session_user_id, _) in list(self._web_sessions.items()):
                if session_user_id == holder.id:
                    del self._web_sessions[token_hash]
        user = self._web_users.get(user_id)
        if user is None:
            raise LookupError("Аккаунт не найден")
        self._web_users[user_id] = replace(user, telegram_id=telegram_id)

    # ---------- поддержка ----------

    async def get_support_ticket_thread(
        self,
        ticket_id: int,
        telegram_id: Optional[int] = None,
        message_limit: int = 50,
    ) -> Optional[SupportTicketThread]:
        ticket = self._support_tickets.get(ticket_id)
        if ticket is None or (
            telegram_id is not None and ticket.telegram_id != telegram_id
        ):
            return None
        profile = self._profiles.get(ticket.telegram_id)
        messages = self._support_messages.get(ticket_id, [])[-message_limit:]
        return SupportTicketThread(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            user_name=profile.user_name if profile else "Участник",
            messages=tuple(
                SupportThreadMessage(
                    id=index + 1,
                    sender_role=message.sender_role,
                    body=message.body,
                    created_at=message.created_at or ticket.updated_at,
                )
                for index, message in enumerate(messages)
            ),
        )

    async def reopen_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
    ) -> Optional[int]:
        from .repository import SupportMessage

        ticket = self._support_tickets.get(ticket_id)
        if ticket is None:
            return None
        if ticket.status == "open":
            raise SupportTicketStateError("Обращение уже открыто")
        other = next(
            (
                item
                for item in self._support_tickets.values()
                if item.telegram_id == ticket.telegram_id and item.status == "open"
            ),
            None,
        )
        if other is not None:
            raise SupportTicketStateError(
                "У участника уже есть открытое обращение №{}".format(other.id)
            )
        self._support_tickets[ticket_id] = replace(
            ticket, status="open", updated_at=_now()
        )
        self._support_messages.setdefault(ticket_id, []).append(
            SupportMessage(
                ticket_id,
                admin_telegram_id,
                "admin",
                "Обращение снова открыто.",
                created_at=_now(),
            )
        )
        return ticket.telegram_id
