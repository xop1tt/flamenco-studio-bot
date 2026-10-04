"""Фоновая сверка платежей, которые никто не проверил вручную.

ЮKassa в этом проекте не шлёт вебхук (см. CLAUDE.md/аудит безопасности):
платёж подтверждается только тогда, когда ``PaymentService.check_payment``
кто-то вызывает — пользователь нажал "проверить статус" в боте/на сайте,
либо админ. Если пользователь оплатил и не вернулся, платёж остаётся
"pending" в нашей БД сколько угодно долго, даже если ЮKassa его уже провела.
Эта задача периодически делает ту же проверку сама за "забытые" платежи.

Задачу запускают и бот, и веб-API — чтобы сверка не зависела от того,
какой из процессов сейчас работает. Каждую итерацию выполняет только тот,
кто взял advisory-блокировку ``RECONCILIATION_LOCK_ID`` в PostgreSQL;
второй процесс эту итерацию пропускает. Двойного зачисления не будет и без
блокировки (``complete_lesson_payment`` зачисляет ровно один раз и только
этот вызов получает CONFIRMED), блокировка убирает лишние запросы к ЮKassa.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Optional,
    Protocol,
    Sequence,
)

from ..services.payments import PaymentCheckResult, PaymentCheckStatus, PaymentService


# Рядом с MIGRATION_LOCK_ID (715_203_401) в database/repository.py.
RECONCILIATION_LOCK_ID = 715_203_402


class PendingPaymentRecord(Protocol):
    id: int
    telegram_id: int


# Вызывается, когда сверка сама зачислила занятия (статус CONFIRMED —
# зачисление происходит ровно один раз, поэтому и уведомление одно).
# Пользователь, оплативший и не вернувшийся в бота, иначе не узнал бы,
# что занятия уже на балансе.
ConfirmedCallback = Callable[[int, PaymentCheckResult], Awaitable[None]]


class PaymentReconciliationRepository(Protocol):
    async def list_pending_lesson_payments_older_than(
        self,
        cutoff: datetime,
    ) -> Sequence[PendingPaymentRecord]: ...

    def try_advisory_lock(self, lock_id: int) -> AsyncContextManager[bool]: ...


async def reconcile_pending_payments(
    payment_service: PaymentService,
    repository: PaymentReconciliationRepository,
    logger: logging.Logger,
    interval_seconds: float = 300.0,
    stale_after_seconds: float = 600.0,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_confirmed: Optional[ConfirmedCallback] = None,
) -> None:
    if interval_seconds <= 0 or stale_after_seconds <= 0:
        raise ValueError("Интервалы сверки платежей должны быть положительными")

    while True:
        await sleep(interval_seconds)
        try:
            async with repository.try_advisory_lock(RECONCILIATION_LOCK_ID) as locked:
                if not locked:
                    logger.info("Payment reconciliation skipped: running elsewhere")
                    continue
                await _reconcile_stale_payments(
                    payment_service,
                    repository,
                    logger,
                    clock() - timedelta(seconds=stale_after_seconds),
                    on_confirmed,
                )
        except Exception:
            # Например, БД недоступна: следующая итерация попробует снова.
            logger.exception("Payment reconciliation iteration failed")


async def _reconcile_stale_payments(
    payment_service: PaymentService,
    repository: PaymentReconciliationRepository,
    logger: logging.Logger,
    cutoff: datetime,
    on_confirmed: Optional[ConfirmedCallback],
) -> None:
    try:
        pending = await repository.list_pending_lesson_payments_older_than(cutoff)
    except Exception:
        logger.exception("Failed to list pending payments for reconciliation")
        return

    for record in pending:
        await _reconcile_one(payment_service, record, logger, on_confirmed)


async def _reconcile_one(
    payment_service: PaymentService,
    record: PendingPaymentRecord,
    logger: logging.Logger,
    on_confirmed: Optional[ConfirmedCallback] = None,
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
    if result.status is PaymentCheckStatus.CONFIRMED and on_confirmed is not None:
        # Занятия уже зачислены и сохранены; сбой уведомления (например,
        # пользователь заблокировал бота) не должен влиять на сверку.
        try:
            await on_confirmed(record.telegram_id, result)
        except Exception:
            logger.exception(
                "Payment confirmation notification failed payment_id=%s",
                record.id,
            )


def start_reconciliation_task(
    payment_service: PaymentService,
    repository: Any,
    logger: logging.Logger,
    on_confirmed: Optional[ConfirmedCallback] = None,
) -> "asyncio.Task[None] | None":
    """Запускает фоновую сверку, только если оплата вообще настроена.

    ``payment_service.checkout_available`` уже учитывает и наличие ключей
    ЮKassa, и поддержку постоянного хранения платежей репозиторием — те же
    условия, при которых имеет смысл что-то сверять.
    """
    if not payment_service.checkout_available:
        return None
    return asyncio.create_task(
        reconcile_pending_payments(
            payment_service, repository, logger, on_confirmed=on_confirmed
        )
    )
