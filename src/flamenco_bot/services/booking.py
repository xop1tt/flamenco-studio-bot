"""Запись на занятия.

Атомарность (вместимость, дубли, параллельные нажатия) обеспечивает
репозиторий: PostgreSQL блокирует строку слота в транзакции. Сервис не
дублирует эти проверки, а добавляет общие для всех интерфейсов побочные
эффекты.
"""

import logging
from typing import Any, Sequence

from ..class_catalog import CLASS_LABELS
from ..database.repository import ClassBooking, ClassSlot
from ..studio_time import format_studio_datetime
from .notifications import AdminNotifier, NotificationReport


logger = logging.getLogger("bot.services.booking")


class BookingService:
    def __init__(self, repository: Any, notifier: AdminNotifier) -> None:
        self.repository = repository
        self.notifier = notifier

    async def list_available_slots(self, class_key: str) -> Sequence[ClassSlot]:
        return await self.repository.list_available_class_slots(class_key)

    async def book(self, slot_id: int, telegram_id: int) -> ClassBooking:
        """Подтверждает место и списывает 1 lesson_credit.

        ``SlotUnavailableError`` — слот закрыт/заполнен/в прошлом.
        ``InsufficientLessonCreditsError`` — на балансе нет занятий.
        ``BookingCooldownError`` — слот отменён этим же пользователем
        недавно, повторная запись пока недоступна.
        """
        booking = await self.repository.book_class_slot(slot_id, telegram_id)
        logger.info(
            "Class booking confirmed slot_id=%s telegram_id=%s duplicate=%s",
            slot_id,
            telegram_id,
            booking.already_booked,
        )
        return booking

    async def cancel(self, slot_id: int, telegram_id: int) -> bool:
        """Отменяет запись и возвращает кредит.

        ``False``, если запись уже была отменена ранее (идемпотентно).
        ``BookingNotFoundError``/``CancellationWindowExpiredError`` —
        см. ``PostgresRepository.cancel_class_slot_booking``.
        """
        cancelled = await self.repository.cancel_class_slot_booking(
            slot_id, telegram_id
        )
        logger.info(
            "Class booking cancel slot_id=%s telegram_id=%s cancelled=%s",
            slot_id,
            telegram_id,
            cancelled,
        )
        return cancelled

    async def notify_admins_about_booking(
        self,
        booking: ClassBooking,
        participant_name: str,
    ) -> NotificationReport:
        report = await self.notifier.notify(
            "Новая запись №{}: {} — {}, участник {} (ID {}).".format(
                booking.id,
                CLASS_LABELS[booking.class_key],
                format_studio_datetime(booking.starts_at),
                participant_name,
                booking.telegram_id,
            ),
            event="class_booking",
        )
        if not report.complete:
            logger.error(
                "Class booking confirmed without notifying all admins "
                "booking_id=%s recipients=%s delivered=%s",
                booking.id,
                report.recipients,
                report.delivered,
            )
        return report
