import json
import unittest
from unittest.mock import patch

from flamenco_bot.payments import PaymentProviderError, YooKassaClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        _ = (exc_type, exc, traceback)
        return False

    def read(self):
        return self.payload


class YooKassaClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = YooKassaClient(
            "shop-123",
            "secret-test",
            "https://t.me/test_bot",
        )

    async def test_create_payment_uses_rub_amount_redirect_and_idempotence(self):
        provider_response = {
            "id": "provider-id",
            "status": "pending",
            "amount": {"value": "3600.00", "currency": "RUB"},
            "confirmation": {"confirmation_url": "https://pay.example/confirm"},
            "metadata": {"telegram_id": "123"},
        }
        with patch(
            "flamenco_bot.payments.client.urlopen",
            return_value=FakeResponse(provider_response),
        ) as urlopen:
            payment = await self.client.create_payment(
                amount_minor=360000,
                description="Абонемент на 4 занятия",
                telegram_id=123,
                package_key="pack_4",
                idempotence_key="checkout-stable-key",
            )

        self.assertEqual(payment.payment_id, "provider-id")
        self.assertEqual(payment.amount_minor, 360000)
        self.assertEqual(payment.currency, "RUB")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.method, "POST")
        self.assertEqual(payload["amount"], {"value": "3600.00", "currency": "RUB"})
        self.assertEqual(payload["confirmation"]["return_url"], "https://t.me/test_bot")
        self.assertEqual(payload["metadata"]["telegram_id"], "123")
        self.assertEqual(request.get_header("Idempotence-key"), "checkout-stable-key")
        self.assertNotIn("secret-test", request.get_header("Authorization"))

    async def test_payment_status_request_uses_escaped_provider_resource_path(self):
        provider_response = {
            "id": "provider-id",
            "status": "succeeded",
            "amount": {"value": "1000.00", "currency": "RUB"},
            "metadata": {"telegram_id": "123"},
        }
        with patch(
            "flamenco_bot.payments.client.urlopen",
            return_value=FakeResponse(provider_response),
        ) as urlopen:
            payment = await self.client.get_payment("provider/id")

        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(
            urlopen.call_args.args[0].full_url,
            "https://api.yookassa.ru/v3/payments/provider%2Fid",
        )

    async def test_refund_uses_persisted_idempotence_key(self):
        provider_response = {
            "id": "refund-id",
            "payment_id": "provider-id",
            "status": "succeeded",
            "amount": {"value": "3600.00", "currency": "RUB"},
        }
        with patch(
            "flamenco_bot.payments.client.urlopen",
            return_value=FakeResponse(provider_response),
        ) as urlopen:
            refund = await self.client.create_refund(
                "provider-id",
                360000,
                "Client request",
                "refund-stable-key",
            )

        self.assertEqual(refund.refund_id, "refund-id")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Idempotence-key"), "refund-stable-key")
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8"))["payment_id"], "provider-id"
        )

    async def test_checkout_requires_credentials_and_valid_provider_response(self):
        unconfigured = YooKassaClient("", "", "https://t.me")
        with self.assertRaisesRegex(PaymentProviderError, "не настроена"):
            await unconfigured.create_payment(
                100000,
                "Разовое занятие",
                123,
                "single",
                "stable-key",
            )

        with self.assertRaisesRegex(PaymentProviderError, "Некорректный ответ"):
            self.client._parse_payment({"id": "bad", "status": "pending"})
