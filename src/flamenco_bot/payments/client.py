import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger("bot.payments")
YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


class PaymentProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderPayment:
    payment_id: str
    status: str
    amount_minor: int
    currency: str
    confirmation_url: Optional[str]
    metadata: Dict[str, Any]


class YooKassaClient:
    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        return_url: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.shop_id = shop_id.strip()
        self.secret_key = secret_key.strip()
        self.return_url = return_url.strip()
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.shop_id and self.secret_key and self.return_url)

    async def create_payment(
        self,
        amount_minor: int,
        description: str,
        telegram_id: int,
        package_key: str,
    ) -> ProviderPayment:
        if not self.is_configured:
            raise PaymentProviderError("ЮKassa не настроена")
        if amount_minor <= 0:
            raise ValueError("Сумма оплаты должна быть положительной")

        idempotence_key = str(uuid.uuid4())
        payload = {
            "amount": {
                "value": "{:.2f}".format(Decimal(amount_minor) / 100),
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self.return_url,
            },
            "description": description[:128],
            "metadata": {
                "telegram_id": str(telegram_id),
                "package_key": package_key,
            },
        }
        response = await asyncio.to_thread(
            self._request,
            "POST",
            "/payments",
            payload,
            idempotence_key,
        )
        return self._parse_payment(response)

    async def get_payment(self, payment_id: str) -> ProviderPayment:
        if not self.is_configured:
            raise PaymentProviderError("ЮKassa не настроена")
        response = await asyncio.to_thread(
            self._request,
            "GET",
            "/payments/{}".format(payment_id),
            None,
            None,
        )
        return self._parse_payment(response)

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]],
        idempotence_key: Optional[str],
    ) -> Dict[str, Any]:
        credentials = "{}:{}".format(self.shop_id, self.secret_key).encode("utf-8")
        headers = {
            "Authorization": "Basic {}".format(
                base64.b64encode(credentials).decode("ascii")
            ),
            "Accept": "application/json",
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if idempotence_key is not None:
            headers["Idempotence-Key"] = idempotence_key

        request = Request(
            YOOKASSA_API_URL + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            logger.error(
                "YooKassa request failed method=%s status=%s",
                method,
                error.code,
            )
            raise PaymentProviderError(
                "ЮKassa вернула HTTP {}".format(error.code)
            ) from error
        except (
            URLError,
            OSError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as error:
            logger.error(
                "YooKassa request unavailable method=%s error_type=%s",
                method,
                type(error).__name__,
            )
            raise PaymentProviderError(
                "Не удалось связаться с ЮKassa"
            ) from error

        if not isinstance(decoded, dict):
            raise PaymentProviderError("Некорректный ответ ЮKassa")
        return decoded

    @staticmethod
    def _parse_payment(response: Dict[str, Any]) -> ProviderPayment:
        try:
            payment_id = response["id"]
            status = response["status"]
            amount = response["amount"]
            amount_minor = int(Decimal(str(amount["value"])) * 100)
            currency = amount["currency"]
            confirmation = response.get("confirmation") or {}
            confirmation_url = confirmation.get("confirmation_url")
            metadata = response.get("metadata") or {}
        except (KeyError, TypeError, ValueError, DecimalException) as error:
            raise PaymentProviderError("Некорректный ответ ЮKassa") from error
        if not isinstance(payment_id, str) or not isinstance(status, str):
            raise PaymentProviderError("Некорректный ответ ЮKassa")
        return ProviderPayment(
            payment_id=payment_id,
            status=status,
            amount_minor=amount_minor,
            currency=currency,
            confirmation_url=confirmation_url,
            metadata=metadata,
        )
