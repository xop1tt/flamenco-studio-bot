"""Прямые тесты ``PaymentService`` с замоканными репозиторием и шлюзом.

Репозиторий и HTTP-клиент ЮKassa уже покрыты отдельно (``test_repository.py``,
``test_payments.py``); здесь проверяется сам сервис — ветки ``check_payment``
и ``process_refund``, которые до этого не были покрыты ни одним тестом.
"""

import unittest
import uuid
from unittest.mock import AsyncMock

from flamenco_bot.database.repository import LessonPayment, LessonRefund
from flamenco_bot.payments import PaymentProviderError
from flamenco_bot.payments.client import ProviderPayment, ProviderRefund
from flamenco_bot.services.payments import (
    PaymentCheckStatus,
    PaymentService,
    RefundStatus,
)


def make_payment(**overrides):
    defaults = dict(
        id=8,
        telegram_id=1001,
        package_key="single",
        lessons=1,
        amount_minor=100000,
        provider_payment_id="provider-payment-1",
        confirmation_url="https://pay.example.test/confirm/1",
        status="pending",
    )
    defaults.update(overrides)
    return LessonPayment(**defaults)


def make_provider_payment(**overrides):
    defaults = dict(
        payment_id="provider-payment-1",
        status="succeeded",
        amount_minor=100000,
        currency="RUB",
        confirmation_url=None,
        metadata={"telegram_id": "1001", "package_key": "single"},
    )
    defaults.update(overrides)
    return ProviderPayment(**defaults)


def make_refund(**overrides):
    defaults = dict(
        payment_id=8,
        telegram_id=1001,
        provider_payment_id="provider-payment-1",
        amount_minor=100000,
        lessons=1,
        idempotence_key=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        provider_refund_id=None,
        reason="Административный возврат",
    )
    defaults.update(overrides)
    return LessonRefund(**defaults)


def make_provider_refund(**overrides):
    defaults = dict(
        refund_id="refund-1",
        payment_id="provider-payment-1",
        status="succeeded",
        amount_minor=100000,
        currency="RUB",
    )
    defaults.update(overrides)
    return ProviderRefund(**defaults)


class CheckPaymentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = AsyncMock()
        self.gateway = AsyncMock()
        self.service = PaymentService(self.repository, self.gateway)

    async def test_not_found(self):
        self.repository.get_lesson_payment.return_value = None

        result = await self.service.check_payment(999, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.NOT_FOUND)
        self.gateway.get_payment.assert_not_awaited()

    async def test_already_succeeded_short_circuits_without_calling_gateway(self):
        self.repository.get_lesson_payment.return_value = make_payment(
            status="succeeded"
        )
        self.repository.get_lesson_credits.return_value = 4

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.ALREADY_SUCCEEDED)
        self.assertEqual(result.credits, 4)
        self.gateway.get_payment.assert_not_awaited()

    async def test_canceled_short_circuits_without_calling_gateway(self):
        self.repository.get_lesson_payment.return_value = make_payment(
            status="canceled"
        )

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.CANCELED)
        self.gateway.get_payment.assert_not_awaited()

    async def test_refund_pending_short_circuits_without_calling_gateway(self):
        self.repository.get_lesson_payment.return_value = make_payment(
            status="refund_pending"
        )

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.REFUND_PENDING)
        self.gateway.get_payment.assert_not_awaited()

    async def test_provider_unavailable_when_gateway_raises(self):
        self.repository.get_lesson_payment.return_value = make_payment()
        self.gateway.get_payment.side_effect = PaymentProviderError("timeout")

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.PROVIDER_UNAVAILABLE)
        self.repository.complete_lesson_payment.assert_not_awaited()

    async def test_mismatch_when_amount_differs(self):
        self.repository.get_lesson_payment.return_value = make_payment()
        self.gateway.get_payment.return_value = make_provider_payment(amount_minor=1)

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.MISMATCH)
        self.repository.complete_lesson_payment.assert_not_awaited()

    async def test_mismatch_when_telegram_id_differs(self):
        self.repository.get_lesson_payment.return_value = make_payment()
        self.gateway.get_payment.return_value = make_provider_payment(
            metadata={"telegram_id": "9999", "package_key": "single"}
        )

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.MISMATCH)

    async def test_confirmed_credits_lessons_exactly_once(self):
        self.repository.get_lesson_payment.return_value = make_payment()
        self.gateway.get_payment.return_value = make_provider_payment(
            status="succeeded"
        )
        self.repository.complete_lesson_payment.return_value = True
        self.repository.get_lesson_credits.return_value = 1

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.CONFIRMED)
        self.assertEqual(result.credits, 1)
        self.repository.complete_lesson_payment.assert_awaited_once_with(8, 1001)

    async def test_already_processed_when_completion_loses_the_race(self):
        """Повторная проверка после того, как платёж уже был зачислен."""
        self.repository.get_lesson_payment.side_effect = [
            make_payment(status="pending"),
            make_payment(status="succeeded"),
        ]
        self.gateway.get_payment.return_value = make_provider_payment(
            status="succeeded"
        )
        self.repository.complete_lesson_payment.return_value = False
        self.repository.get_lesson_credits.return_value = 1

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.ALREADY_PROCESSED)
        self.assertEqual(result.credits, 1)

    async def test_status_changed_when_payment_was_canceled_concurrently(self):
        self.repository.get_lesson_payment.side_effect = [
            make_payment(status="pending"),
            make_payment(status="canceled"),
        ]
        self.gateway.get_payment.return_value = make_provider_payment(
            status="succeeded"
        )
        self.repository.complete_lesson_payment.return_value = False

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.STATUS_CHANGED)
        self.assertEqual(result.payment.status, "canceled")

    async def test_provider_canceled_marks_payment_canceled(self):
        self.repository.get_lesson_payment.return_value = make_payment()
        self.gateway.get_payment.return_value = make_provider_payment(status="canceled")

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.PROVIDER_CANCELED)
        self.repository.cancel_lesson_payment.assert_awaited_once_with(8, 1001)

    async def test_pending_when_provider_has_not_decided_yet(self):
        self.repository.get_lesson_payment.return_value = make_payment()
        self.gateway.get_payment.return_value = make_provider_payment(status="pending")

        result = await self.service.check_payment(8, 1001)

        self.assertEqual(result.status, PaymentCheckStatus.PENDING)
        self.repository.complete_lesson_payment.assert_not_awaited()
        self.repository.cancel_lesson_payment.assert_not_awaited()


class ProcessRefundTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = AsyncMock()
        self.gateway = AsyncMock()
        self.service = PaymentService(self.repository, self.gateway)

    async def test_invalid_when_repository_rejects_the_request(self):
        self.repository.prepare_lesson_refund.side_effect = ValueError(
            "Занятия уже использованы"
        )

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.INVALID)
        self.assertIn("использованы", result.error_message)

    async def test_unavailable_when_no_payment_to_refund(self):
        self.repository.prepare_lesson_refund.return_value = None

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.UNAVAILABLE)

    async def test_provider_unavailable_when_gateway_create_refund_fails(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.side_effect = PaymentProviderError("timeout")

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.PROVIDER_UNAVAILABLE)
        self.repository.record_provider_refund.assert_not_awaited()

    async def test_resumes_existing_refund_via_get_instead_of_create(self):
        self.repository.prepare_lesson_refund.return_value = make_refund(
            provider_refund_id="refund-1"
        )
        self.gateway.get_refund.return_value = make_provider_refund(status="pending")

        result = await self.service.process_refund(8, admin_id=77)

        self.gateway.get_refund.assert_awaited_once_with("refund-1")
        self.gateway.create_refund.assert_not_awaited()
        self.assertEqual(result.status, RefundStatus.PENDING)

    async def test_mismatch_when_provider_amount_differs(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(amount_minor=1)

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.MISMATCH)
        self.repository.complete_lesson_refund.assert_not_awaited()

    async def test_completed_when_provider_refund_succeeds(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(
            status="succeeded"
        )
        self.repository.complete_lesson_refund.return_value = True

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.COMPLETED)
        self.assertEqual(result.lessons, 1)
        self.assertEqual(result.provider_refund_id, "refund-1")

    async def test_already_processed_when_completion_loses_the_race(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(
            status="succeeded"
        )
        self.repository.complete_lesson_refund.return_value = False

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.ALREADY_PROCESSED)

    async def test_pending_when_provider_has_not_decided_yet(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(status="pending")

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.PENDING)
        self.repository.complete_lesson_refund.assert_not_awaited()

    async def test_released_when_provider_cancels_the_refund(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(
            status="canceled"
        )
        self.repository.release_lesson_refund.return_value = True

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.RELEASED)

    async def test_unresolved_when_provider_cancels_but_release_fails(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(
            status="canceled"
        )
        self.repository.release_lesson_refund.return_value = False

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.UNRESOLVED)

    async def test_unresolved_for_an_unexpected_provider_status(self):
        self.repository.prepare_lesson_refund.return_value = make_refund()
        self.gateway.create_refund.return_value = make_provider_refund(
            status="waiting_for_capture"
        )

        result = await self.service.process_refund(8, admin_id=77)

        self.assertEqual(result.status, RefundStatus.UNRESOLVED)
        self.repository.release_lesson_refund.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
