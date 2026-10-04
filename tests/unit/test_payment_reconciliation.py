"""Фоновая сверка "забытых" pending-платежей (без вебхука ЮKassa)."""

import logging
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from flamenco_bot.runtime.payment_reconciliation import (
    reconcile_pending_payments,
    start_reconciliation_task,
)
from flamenco_bot.services.payments import PaymentCheckResult, PaymentCheckStatus


@dataclass(frozen=True)
class _Record:
    id: int
    telegram_id: int


class ReconcilePendingPaymentsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = logging.getLogger("test.payment_reconciliation")
        self.repository = AsyncMock()
        self.payment_service = AsyncMock()

    async def _run_one_tick(self, **kwargs):
        """Запускает цикл и останавливает его после первой итерации."""

        class _StopAfterOneTick(Exception):
            pass

        ticks = {"count": 0}

        async def sleep(_seconds):
            ticks["count"] += 1
            if ticks["count"] > 1:
                raise _StopAfterOneTick

        with self.assertRaises(_StopAfterOneTick):
            await reconcile_pending_payments(
                self.payment_service,
                self.repository,
                self.logger,
                sleep=sleep,
                clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
                **kwargs,
            )

    async def test_checks_every_pending_payment_returned_by_the_repository(self):
        self.repository.list_pending_lesson_payments_older_than.return_value = [
            _Record(id=1, telegram_id=100),
            _Record(id=2, telegram_id=200),
        ]
        self.payment_service.check_payment.return_value = PaymentCheckResult(
            PaymentCheckStatus.PENDING
        )

        await self._run_one_tick()

        self.assertEqual(self.payment_service.check_payment.await_count, 2)
        self.payment_service.check_payment.assert_any_await(1, 100)
        self.payment_service.check_payment.assert_any_await(2, 200)

    async def test_one_failing_check_does_not_stop_the_rest(self):
        self.repository.list_pending_lesson_payments_older_than.return_value = [
            _Record(id=1, telegram_id=100),
            _Record(id=2, telegram_id=200),
        ]
        self.payment_service.check_payment.side_effect = [
            RuntimeError("ЮKassa недоступна"),
            PaymentCheckResult(PaymentCheckStatus.CONFIRMED),
        ]

        await self._run_one_tick()

        self.assertEqual(self.payment_service.check_payment.await_count, 2)

    async def test_user_is_notified_only_when_sweep_credits_lessons(self):
        self.repository.list_pending_lesson_payments_older_than.return_value = [
            _Record(id=1, telegram_id=100),
            _Record(id=2, telegram_id=200),
            _Record(id=3, telegram_id=300),
        ]
        confirmed = PaymentCheckResult(PaymentCheckStatus.CONFIRMED, credits=4)
        self.payment_service.check_payment.side_effect = [
            PaymentCheckResult(PaymentCheckStatus.PENDING),
            confirmed,
            PaymentCheckResult(PaymentCheckStatus.ALREADY_SUCCEEDED, credits=4),
        ]
        on_confirmed = AsyncMock()

        await self._run_one_tick(on_confirmed=on_confirmed)

        on_confirmed.assert_awaited_once_with(200, confirmed)

    async def test_notification_failure_does_not_stop_the_sweep(self):
        self.repository.list_pending_lesson_payments_older_than.return_value = [
            _Record(id=1, telegram_id=100),
            _Record(id=2, telegram_id=200),
        ]
        self.payment_service.check_payment.return_value = PaymentCheckResult(
            PaymentCheckStatus.CONFIRMED
        )
        on_confirmed = AsyncMock(side_effect=RuntimeError("bot blocked"))

        await self._run_one_tick(on_confirmed=on_confirmed)

        self.assertEqual(self.payment_service.check_payment.await_count, 2)
        self.assertEqual(on_confirmed.await_count, 2)

    async def test_listing_failure_is_logged_and_does_not_crash_the_loop(self):
        self.repository.list_pending_lesson_payments_older_than.side_effect = (
            RuntimeError("БД недоступна")
        )

        await self._run_one_tick()

        self.payment_service.check_payment.assert_not_awaited()

    async def test_invalid_intervals_are_rejected(self):
        with self.assertRaises(ValueError):
            await reconcile_pending_payments(
                self.payment_service,
                self.repository,
                self.logger,
                interval_seconds=0,
            )


class StartReconciliationTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_task_is_started_when_checkout_is_unavailable(self):
        payment_service = AsyncMock()
        type(payment_service).checkout_available = False

        task = start_reconciliation_task(
            payment_service,
            repository=AsyncMock(),
            logger=logging.getLogger("test.payment_reconciliation"),
        )

        self.assertIsNone(task)

    async def test_task_is_started_when_checkout_is_available(self):
        payment_service = AsyncMock()
        type(payment_service).checkout_available = True
        repository = AsyncMock()
        repository.list_pending_lesson_payments_older_than.return_value = []

        task = start_reconciliation_task(
            payment_service,
            repository,
            logging.getLogger("test.payment_reconciliation"),
        )
        try:
            self.assertIsNotNone(task)
        finally:
            task.cancel()
            with self.assertRaises(BaseException):
                await task


if __name__ == "__main__":
    unittest.main()
