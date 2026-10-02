"""FastAPI-зависимости: репозиторий, сервисы, текущий пользователь."""

from typing import Any, Optional

from fastapi import Cookie, HTTPException, Request, status

from ..database.repository import WebUserRecord
from ..services import AuthService
from .security import SESSION_COOKIE_NAME, read_session_user_id


def get_repository(request: Request) -> Any:
    return request.app.state.repository


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_session_secret_key(request: Request) -> str:
    return request.app.state.session_secret_key


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
