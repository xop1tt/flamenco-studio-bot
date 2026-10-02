"""Фоновая сверка платежей, которые никто не проверил вручную.

ЮKassa в этом проекте не шлёт вебхук (см. CLAUDE.md/аудит безопасности):
платёж подтверждается только тогда, когда ``PaymentService.check_payment``
кто-то вызывает — пользователь нажал "проверить статус" в боте/на сайте,
либо админ. Если пользователь оплатил и не вернулся, платёж остаётся
"pending" в нашей БД сколько угодно долго, даже если ЮKassa его уже провела.
Эта задача периодически делает ту же проверку сама за "забытые" платежи.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Protocol, Sequence

from ..services.payments import PaymentCheckStatus, PaymentService


class PendingPaymentRecord(Protocol):
    id: int
    telegram_id: int


class PaymentReconciliationRepository(Protocol):
    async def list_pending_lesson_payments_older_than(
        self,
        cutoff: datetime,
    ) -> Sequence[PendingPaymentRecord]: ...


async def reconcile_pending_payments(
    payment_service: PaymentService,
    repository: PaymentReconciliationRepository,
    logger: logging.Logger,
    interval_seconds: float = 300.0,
    stale_after_seconds: float = 600.0,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    if interval_seconds <= 0 or stale_after_seconds <= 0:
        raise ValueError("Интервалы сверки платежей должны быть положительными")

    while True:
        await sleep(interval_seconds)
        cutoff = clock() - timedelta(seconds=stale_after_seconds)
        try:
            pending = await repository.list_pending_lesson_payments_older_than(cutoff)
        except Exception:
            logger.exception("Failed to list pending payments for reconciliation")
            continue

        for record in pending:
            await _reconcile_one(payment_service, record, logger)


async def _reconcile_one(
    payment_service: PaymentService,
    record: PendingPaymentRecord,
    logger: logging.Logger,
) -> None:
    try:
        result = await payment_service.check_payment(record.id, record.telegram_id)
    except Exception:
        logger.exception(
            "Payment reconciliation check failed payment_id=%s",
            record.id,
        )
        return
    if result.status is PaymentCheckStatus.PENDING:
        return
    logger.info(
        "Reconciled stale payment payment_id=%s telegram_id=%s result=%s",
        record.id,
        record.telegram_id,
        result.status.value,
    )


def start_reconciliation_task(
    payment_service: PaymentService,
    repository: Any,
    logger: logging.Logger,
) -> "asyncio.Task[None] | None":
    """Запускает фоновую сверку, только если оплата вообще настроена.

    ``payment_service.checkout_available`` уже учитывает и наличие ключей
    ЮKassa, и поддержку постоянного хранения платежей репозиторием — те же
    условия, при которых имеет смысл что-то сверять.
    """
    if not payment_service.checkout_available:
        return None
    return asyncio.create_task(
        reconcile_pending_payments(payment_service, repository, logger)
    )
