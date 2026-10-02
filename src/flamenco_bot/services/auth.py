"""Вход на сайт по email/паролю или через привязанный Telegram.

Используется только веб-интерфейсом: Telegram-бот продолжает опознавать
пользователей по telegram_id через ``bot_users``/``get_or_create_profile``
и не зависит от этого модуля.

Веб-аккаунт (``users``) не владеет бизнес-данными бота — он лишь хранит,
какой telegram_id сейчас привязан. Смена привязки — это обновление одной
строки в ``users``; история платежей/записей остаётся там, где её ведёт бот
(под тем telegram_id, который привязан в данный момент).
"""

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any, Mapping

from ..database.repository import (
    EmailAlreadyRegisteredError,
    TelegramAlreadyLinkedError,
    WebUserRecord,
)


logger = logging.getLogger("bot.services.auth")

MIN_PASSWORD_LENGTH = 8
_TELEGRAM_AUTH_MAX_AGE_SECONDS = 24 * 60 * 60
# PBKDF2-HMAC-SHA256: доступен в любой сборке hashlib (в отличие от scrypt,
# который на некоторых платформах требует OpenSSL с поддержкой scrypt).
# Итерации — по рекомендации OWASP (2023) для PBKDF2-SHA256.
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_DERIVED_KEY_LENGTH = 32


class WeakPasswordError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class InvalidTelegramAuthError(ValueError):
    """Подпись или срок действия данных Telegram Login Widget не прошли проверку."""


class CannotUnlinkOnlyLoginMethodError(ValueError):
    """Нельзя отвязать Telegram, если это единственный способ входа в аккаунт."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_DERIVED_KEY_LENGTH,
    )
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS, salt.hex(), derived.hex()
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, derived_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(derived_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        int(iterations),
        dklen=len(expected),
    )
    return hmac.compare_digest(candidate, expected)


def verify_telegram_login(
    payload: Mapping[str, Any],
    bot_token: str,
    max_age_seconds: int = _TELEGRAM_AUTH_MAX_AGE_SECONDS,
) -> int:
    """Проверяет подпись Telegram Login Widget и возвращает telegram_id.

    См. https://core.telegram.org/widgets/login#checking-authorization
    """
    data = dict(payload)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InvalidTelegramAuthError("Отсутствует подпись Telegram")

    check_string = "\n".join(
        "{}={}".format(key, data[key]) for key in sorted(data) if data[key] is not None
    )
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed_hash = hmac.new(
        secret_key, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed_hash, str(received_hash)):
        raise InvalidTelegramAuthError("Подпись Telegram не прошла проверку")

    try:
        auth_timestamp = int(data["auth_date"])
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidTelegramAuthError(
            "Некорректная дата авторизации Telegram"
        ) from error
    if time.time() - auth_timestamp > max_age_seconds:
        raise InvalidTelegramAuthError("Срок действия входа через Telegram истёк")

    try:
        telegram_id = int(data["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidTelegramAuthError("Отсутствует Telegram ID") from error
    if telegram_id <= 0:
        raise InvalidTelegramAuthError("Некорректный Telegram ID")
    return telegram_id


def _telegram_display_name(payload: Mapping[str, Any]) -> str:
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)
    return full_name or "Участник студии"


class AuthService:
    def __init__(self, repository: Any, bot_token: str) -> None:
        self.repository = repository
        self.bot_token = bot_token

    async def register_with_email(
        self,
        email: str,
        password: str,
        display_name: str,
    ) -> WebUserRecord:
        normalized_email = email.strip().lower()
        if not normalized_email or "@" not in normalized_email:
            raise ValueError("Укажите корректный email")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(
                "Пароль должен содержать минимум {} символов".format(
                    MIN_PASSWORD_LENGTH
                )
            )
        normalized_name = display_name.strip() or "Участник студии"
        user = await self.repository.create_web_user(
            normalized_email, hash_password(password), normalized_name
        )
        logger.info("Registered web user user_id=%s", user.id)
        return user

    async def authenticate_with_email(
        self,
        email: str,
        password: str,
    ) -> WebUserRecord:
        user = await self.repository.get_web_user_by_email(email.strip().lower())
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            logger.warning("Email authentication failed email_present=%s", bool(email))
            raise InvalidCredentialsError("Неверный email или пароль")
        return user

    async def login_with_telegram(self, payload: Mapping[str, Any]) -> WebUserRecord:
        telegram_id = verify_telegram_login(payload, self.bot_token)
        display_name = _telegram_display_name(payload)
        # Гарантируем, что у Telegram-идентичности есть профиль бота: та же
        # запись bot_users, которую видит и использует сам бот.
        await self.repository.get_or_create_profile(
            telegram_id=telegram_id,
            user_name=display_name,
            is_admin=False,
        )
        user = await self.repository.get_or_create_web_user_from_telegram(
            telegram_id, display_name
        )
        logger.info("Telegram login succeeded user_id=%s", user.id)
        return user

    async def link_telegram(
        self,
        user_id: int,
        payload: Mapping[str, Any],
    ) -> WebUserRecord:
        telegram_id = verify_telegram_login(payload, self.bot_token)
        display_name = _telegram_display_name(payload)
        await self.repository.get_or_create_profile(
            telegram_id=telegram_id,
            user_name=display_name,
            is_admin=False,
        )
        try:
            await self.repository.set_web_user_telegram_id(user_id, telegram_id)
        except TelegramAlreadyLinkedError:
            logger.warning("Telegram link rejected: already linked user_id=%s", user_id)
            raise
        logger.info("Linked Telegram to web account user_id=%s", user_id)
        updated = await self.repository.get_web_user_by_id(user_id)
        if updated is None:
            raise LookupError("Аккаунт не найден")
        return updated

    async def unlink_telegram(self, user_id: int) -> WebUserRecord:
        user = await self.repository.get_web_user_by_id(user_id)
        if user is None:
            raise LookupError("Аккаунт не найден")
        if user.email is None:
            raise CannotUnlinkOnlyLoginMethodError(
                "Нельзя отвязать Telegram: это единственный способ входа "
                "в аккаунт. Сначала задайте email и пароль."
            )
        await self.repository.set_web_user_telegram_id(user_id, None)
        logger.info("Unlinked Telegram from web account user_id=%s", user_id)
        updated = await self.repository.get_web_user_by_id(user_id)
        if updated is None:
            raise LookupError("Аккаунт не найден")
        return updated


__all__ = [
    "AuthService",
    "CannotUnlinkOnlyLoginMethodError",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "InvalidTelegramAuthError",
    "MIN_PASSWORD_LENGTH",
    "TelegramAlreadyLinkedError",
    "WeakPasswordError",
    "hash_password",
    "verify_password",
    "verify_telegram_login",
]
