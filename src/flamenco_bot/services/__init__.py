"""Общая бизнес-логика для Telegram-бота и веб-интерфейса.

Модули пакета не импортируют обработчики aiogram и не формируют ответы
пользователю: они возвращают результат, а интерфейс решает, как его показать.
"""

from .auth import (
    AuthService,
    CannotUnlinkOnlyLoginMethodError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTelegramAuthError,
    TelegramAlreadyLinkedError,
    WeakPasswordError,
)
from .booking import BookingService
from .notifications import AdminNotifier, NotificationReport
from .profile import (
    MAX_USER_NAME_LENGTH,
    InvalidUserNameError,
    normalize_user_name,
)
from .payments import (
    CheckoutFailedError,
    CheckoutResult,
    CheckoutUnavailableError,
    PaymentCheckResult,
    PaymentCheckStatus,
    PaymentService,
    RefundResult,
    RefundStatus,
)
from .support import (
    SupportMessageInvalidError,
    SupportRateLimitedError,
    SupportService,
    SupportSubmission,
)

__all__ = [
    "AdminNotifier",
    "AuthService",
    "BookingService",
    "CannotUnlinkOnlyLoginMethodError",
    "CheckoutFailedError",
    "CheckoutResult",
    "CheckoutUnavailableError",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "InvalidTelegramAuthError",
    "InvalidUserNameError",
    "MAX_USER_NAME_LENGTH",
    "NotificationReport",
    "PaymentCheckResult",
    "PaymentCheckStatus",
    "PaymentService",
    "RefundResult",
    "RefundStatus",
    "SupportMessageInvalidError",
    "SupportRateLimitedError",
    "SupportService",
    "SupportSubmission",
    "TelegramAlreadyLinkedError",
    "WeakPasswordError",
    "normalize_user_name",
]
