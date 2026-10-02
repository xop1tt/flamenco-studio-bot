"""Регистрация, вход и управление привязкой Telegram: ``/api/auth/*``.

Эндпоинты — тонкая обёртка над ``services.auth.AuthService``: валидируют
вход, вызывают сервис, превращают его исключения в HTTP-ответы. Вся бизнес-
логика (проверка пароля, подписи Telegram, уникальности) — в сервисе, а не
здесь, чтобы её не продублировать для бота и сайта.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ...services import (
    AuthService,
    CannotUnlinkOnlyLoginMethodError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTelegramAuthError,
    TelegramAlreadyLinkedError,
    WeakPasswordError,
)
from ...database.repository import WebUserRecord
from ..dependencies import get_auth_service, get_current_user, get_session_secret_key
from ..schemas import LoginRequest, RegisterRequest, TelegramAuthRequest, UserResponse
from ..security import (
    SESSION_COOKIE_NAME,
    SESSION_TOKEN_TTL_SECONDS,
    create_session_token,
)


logger = logging.getLogger("bot.api.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, user_id: int, secret_key: str) -> None:
    token = create_session_token(user_id, secret_key)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    secret_key: str = Depends(get_session_secret_key),
) -> UserResponse:
    try:
        user = await auth_service.register_with_email(
            payload.email, payload.password, payload.display_name
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except WeakPasswordError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    _set_session_cookie(response, user.id, secret_key)
    return UserResponse.from_record(user)


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    secret_key: str = Depends(get_session_secret_key),
) -> UserResponse:
    try:
        user = await auth_service.authenticate_with_email(
            payload.email, payload.password
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    _set_session_cookie(response, user.id, secret_key)
    return UserResponse.from_record(user)


@router.post("/telegram", response_model=UserResponse)
async def login_with_telegram(
    payload: TelegramAuthRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    secret_key: str = Depends(get_session_secret_key),
) -> UserResponse:
    try:
        user = await auth_service.login_with_telegram(payload.to_payload())
    except InvalidTelegramAuthError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    _set_session_cookie(response, user.id, secret_key)
    return UserResponse.from_record(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: WebUserRecord = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.from_record(current_user)


@router.post("/me/telegram", response_model=UserResponse)
async def link_telegram(
    payload: TelegramAuthRequest,
    current_user: WebUserRecord = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = await auth_service.link_telegram(current_user.id, payload.to_payload())
    except InvalidTelegramAuthError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    except TelegramAlreadyLinkedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return UserResponse.from_record(user)


@router.delete("/me/telegram", response_model=UserResponse)
async def unlink_telegram(
    current_user: WebUserRecord = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    try:
        user = await auth_service.unlink_telegram(current_user.id)
    except CannotUnlinkOnlyLoginMethodError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return UserResponse.from_record(user)
