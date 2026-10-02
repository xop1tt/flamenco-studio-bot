"""Подпись и проверка сессионных cookie веб-API.

Используется только веб-слоем. Telegram-бот не формирует и не проверяет эти
токены — у него своя собственная модель доступа (``runtime.admin_access``).
"""

import time
from typing import Optional

import jwt


SESSION_COOKIE_NAME = "session"
SESSION_TOKEN_ALGORITHM = "HS256"
SESSION_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def create_session_token(user_id: int, secret_key: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + SESSION_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, secret_key, algorithm=SESSION_TOKEN_ALGORITHM)


def read_session_user_id(token: str, secret_key: str) -> Optional[int]:
    """Возвращает user_id из валидного токена или None для любой ошибки."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[SESSION_TOKEN_ALGORITHM])
    except jwt.PyJWTError:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
