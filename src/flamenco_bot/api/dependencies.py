"""FastAPI-зависимости: репозиторий, сервисы, текущий пользователь."""

from typing import Any, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status

from ..database.repository import WebUserRecord
from ..runtime.security import SupportRateLimiter
from ..services import (
    AdminNotifier,
    AuthService,
    BookingService,
    PaymentService,
    SupportService,
)
from .security import SESSION_COOKIE_NAME, read_session_user_id


def get_repository(request: Request) -> Any:
    return request.app.state.repository


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_session_secret_key(request: Request) -> str:
    return request.app.state.session_secret_key


def get_bot(request: Request) -> Any:
    return request.app.state.bot


def get_support_limiter(request: Request) -> SupportRateLimiter:
    return request.app.state.support_limiter


def get_payment_gateway(request: Request) -> Any:
    return request.app.state.payment_gateway


async def get_current_user(
    request: Request,
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> WebUserRecord:
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")
    user_id = read_session_user_id(session, get_session_secret_key(request))
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    user = await get_repository(request).get_web_user_by_id(user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Аккаунт не найден")
    return user


async def require_telegram_linked_user(
    current_user: WebUserRecord = Depends(get_current_user),
) -> WebUserRecord:
    """Бронирование, баланс занятий и поддержка в БД привязаны к telegram_id

    (``bot_users``), а не к веб-аккаунту напрямую — так уже устроена схема,
    которой пользуется и бот. Поэтому эти действия на сайте требуют
    привязанного Telegram, а не только входа по email.
    """
    if current_user.telegram_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Привяжите Telegram к аккаунту, чтобы использовать эту функцию",
        )
    return current_user


def get_admin_notifier(request: Request) -> AdminNotifier:
    return AdminNotifier(get_bot(request), get_repository(request))


def get_booking_service(request: Request) -> BookingService:
    return BookingService(get_repository(request), get_admin_notifier(request))


def get_support_service(request: Request) -> SupportService:
    return SupportService(
        get_repository(request),
        get_support_limiter(request),
        get_admin_notifier(request),
    )


def get_payment_service(request: Request) -> PaymentService:
    return PaymentService(get_repository(request), get_payment_gateway(request))
