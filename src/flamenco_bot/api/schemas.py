"""Pydantic-схемы запросов/ответов веб-API.

Явные схемы вместо прямой отдачи объектов репозитория — ``password_hash`` и
другие внутренние поля никогда не попадают в ответ.
"""

from datetime import datetime
from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field

from ..database.repository import WebUserRecord


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class TelegramAuthRequest(BaseModel):
    """Данные, которые Telegram Login Widget передаёт фронтенду.

    Подпись (``hash``) проверяется на backend — см. ``services.auth``.
    """

    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

    def to_payload(self) -> Mapping[str, Any]:
        return self.model_dump(exclude_none=True)


class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    telegram_id: Optional[int]
    display_name: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: WebUserRecord) -> "UserResponse":
        return cls(
            id=record.id,
            email=record.email,
            telegram_id=record.telegram_id,
            display_name=record.display_name,
            created_at=record.created_at,
        )
