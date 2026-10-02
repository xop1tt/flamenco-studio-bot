"""Оплата абонементов: ``/api/payments``.

Тонкая обёртка над ``services.payments.PaymentService`` — тот же checkout,
сверка статуса и идемпотентность, которыми уже пользуется бот. Без
настроенной ЮKassa (``YOOKASSA_SHOP_ID``/``YOOKASSA_SECRET_KEY``/
``WEB_YOOKASSA_RETURN_URL``) или без PostgreSQL (``PaymentService.
checkout_available``) checkout отвечает 503 — ожидаемое состояние, пока
ЮKassa не подключена (см. WEBSITE_PLAN.md, Stage 7).

Подтверждение успешной оплаты никогда не приходит от фронтенда: только
через ``check_payment`` -> запрос статуса у ЮKassa, как и у бота.
"""

import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status

from ...database.repository import WebUserRecord
from ...payments import PURCHASE_PACKAGES
from ...services import CheckoutFailedError, PaymentService
from ..dependencies import (
    get_payment_service,
    get_repository,
    require_telegram_linked_user,
)
from ..schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentHistoryItemResponse,
    PaymentStatusResponse,
)


logger = logging.getLogger("bot.api.payments")
router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_checkout(
    payload: CheckoutRequest,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    payment_service: PaymentService = Depends(get_payment_service),
) -> CheckoutResponse:
    package = next(
        (
            item
            for item in PURCHASE_PACKAGES.values()
            if item.key == payload.package_key
        ),
        None,
    )
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Неизвестный пакет занятий")

    if not payment_service.checkout_available:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Оплата пока недоступна: ЮKassa не настроена",
        )

    try:
        result = await payment_service.start_checkout(current_user.telegram_id, package)
    except CheckoutFailedError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    return CheckoutResponse.from_result(result)


@router.get("/{payment_id}/check", response_model=PaymentStatusResponse)
async def check_payment_status(
    payment_id: int,
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentStatusResponse:
    result = await payment_service.check_payment(payment_id, current_user.telegram_id)
    return PaymentStatusResponse(status=result.status.value, credits=result.credits)


@router.get("/me", response_model=List[PaymentHistoryItemResponse])
async def list_my_payments(
    current_user: WebUserRecord = Depends(require_telegram_linked_user),
    repository: Any = Depends(get_repository),
) -> List[PaymentHistoryItemResponse]:
    payments = await repository.list_lesson_payments_for_telegram_id(
        current_user.telegram_id
    )
    return [PaymentHistoryItemResponse.from_record(payment) for payment in payments]
