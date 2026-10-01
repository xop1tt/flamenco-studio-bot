import errno
import logging
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.parse import urlparse

import asyncpg


logger = logging.getLogger("bot.database")
MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"
MIGRATION_LOCK_ID = 715_203_401


class DatabaseUnavailableError(ConnectionError):
    """Raised when the configured PostgreSQL endpoint cannot be reached."""


@dataclass(frozen=True)
class DatabaseHealth:
    backend: str
    pool_size: int
    idle_connections: int


@dataclass(frozen=True)
class UserStatistics:
    total_users: int
    online_users: int


@dataclass(frozen=True)
class UserProfile:
    telegram_id: int
    phone: Optional[str]
    user_name: str
    registered_at: datetime
    is_admin: bool
    lesson_credits: int = 0

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "UserProfile":
        return cls(
            telegram_id=record["telegram_id"],
            phone=record["phone"],
            user_name=record["user_name"],
            registered_at=record["registered_at"],
            is_admin=record["is_admin"],
            lesson_credits=record.get("lesson_credits", 0),
        )


@dataclass(frozen=True)
class LessonRequest:
    id: int
    telegram_id: int
    kind: str
    details: str
    status: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "LessonRequest":
        return cls(
            id=record["id"],
            telegram_id=record["telegram_id"],
            kind=record["kind"],
            details=record["details"],
            status=record["status"],
            created_at=record["created_at"],
        )


@dataclass(frozen=True)
class LessonPayment:
    id: int
    telegram_id: int
    package_key: str
    lessons: int
    amount_minor: int
    provider_payment_id: str
    confirmation_url: str
    status: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "LessonPayment":
        return cls(
            id=record["id"],
            telegram_id=record["telegram_id"],
            package_key=record["package_key"],
            lessons=record["lessons"],
            amount_minor=record["amount_minor"],
            provider_payment_id=record["provider_payment_id"],
            confirmation_url=record["confirmation_url"],
            status=record["status"],
        )


class PostgresRepository:
    supports_durable_payments = True

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def connect(
        cls,
        database_url: str,
        ssl_ca_path: Optional[str] = None,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
        ssl_mode: str = "verify-full",
        allow_insecure_local: bool = False,
    ) -> "PostgresRepository":
        if not database_url:
            raise ValueError(
                "DATABASE_URL не задан. Настройте защищённое подключение PostgreSQL."
            )

        parsed_url = urlparse(database_url)
        hostname = parsed_url.hostname
        if not hostname or not parsed_url.scheme.startswith("postgres"):
            raise ValueError(
                "DATABASE_URL должен содержать адрес PostgreSQL "
                "в формате postgresql://user:password@host:5432/database."
            )
        if ssl_mode not in {"verify-full", "disable"}:
            raise ValueError("DATABASE_SSL_MODE должен быть verify-full или disable")
        if ssl_mode == "disable":
            try:
                is_loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                is_loopback = hostname.lower() == "localhost"
            if not allow_insecure_local or not is_loopback:
                raise ValueError(
                    "Подключение PostgreSQL без TLS разрешено только для "
                    "localhost в development"
                )
        if pool_min_size < 1 or pool_max_size < pool_min_size:
            raise ValueError(
                "Размер пула PostgreSQL должен удовлетворять "
                "1 <= min_size <= max_size"
            )
        if hostname == "example.com" or hostname.endswith(
            (".example.com", ".example.test")
        ):
            raise ValueError(
                "DATABASE_URL указывает на примерный hostname. "
                "Укажите адрес реального доступного PostgreSQL-сервера."
            )

        ssl_setting: Any
        if ssl_mode == "disable":
            ssl_setting = False
        else:
            ssl_setting = ssl.create_default_context(
                cafile=str(Path(ssl_ca_path).expanduser()) if ssl_ca_path else None
            )
        try:
            pool = await asyncpg.create_pool(
                dsn=database_url,
                ssl=ssl_setting,
                min_size=pool_min_size,
                max_size=pool_max_size,
                command_timeout=30,
            )
        except OSError as error:
            if getattr(error, "errno", None) == socket.EAI_NONAME:
                raise DatabaseUnavailableError(
                    "Не удалось разрешить hostname PostgreSQL. "
                    "Проверьте DATABASE_URL и DNS."
                ) from error
            if getattr(error, "errno", None) in {
                errno.ECONNREFUSED,
                errno.ETIMEDOUT,
                errno.EHOSTUNREACH,
                errno.ENETUNREACH,
            }:
                raise DatabaseUnavailableError(
                    "Не удалось подключиться к PostgreSQL. Убедитесь, что сервер "
                    "запущен и доступен по адресу и порту из DATABASE_URL."
                ) from error
            raise
        logger.info("Connected to PostgreSQL with TLS verification enabled")
        return cls(pool)

    async def initialize(self) -> None:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    MIGRATION_LOCK_ID,
                )
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                records = await connection.fetch(
                    "SELECT version FROM schema_migrations"
                )
                applied_versions = {record["version"] for record in records}
                for migration in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
                    version = migration.name.split("_", 1)[0]
                    if not version.isdigit():
                        raise ValueError(
                            "Имя миграции должно начинаться с числовой версии: "
                            f"{migration.name}"
                        )
                    if version in applied_versions:
                        continue
                    await connection.execute(
                        migration.read_text(encoding="utf-8")
                    )
                    await connection.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
                    applied_versions.add(version)
                    logger.info("Applied database migration version=%s", version)
        logger.info("Database migrations are up to date")

    async def health_check(self) -> DatabaseHealth:
        async with self._pool.acquire() as connection:
            await connection.execute("SELECT 1")
        return DatabaseHealth(
            backend="postgres",
            pool_size=self._pool.get_size(),
            idle_connections=self._pool.get_idle_size(),
        )

    async def record_activity(self, telegram_id: int) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                "UPDATE bot_users SET last_seen_at = NOW() WHERE telegram_id = $1",
                telegram_id,
            )

    async def get_user_statistics(self, online_since: datetime) -> UserStatistics:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                SELECT COUNT(*) AS total_users,
                       COUNT(*) FILTER (WHERE last_seen_at >= $1) AS online_users
                FROM bot_users
                """,
                online_since,
            )
        return UserStatistics(
            total_users=record["total_users"],
            online_users=record["online_users"],
        )

    async def create_lesson_payment(
        self,
        telegram_id: int,
        package_key: str,
        lessons: int,
        amount_minor: int,
        provider_payment_id: str,
        confirmation_url: str,
    ) -> LessonPayment:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                INSERT INTO lesson_payments (
                    telegram_id, package_key, lessons, amount_minor,
                    provider_payment_id, confirmation_url
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, telegram_id, package_key, lessons, amount_minor,
                          provider_payment_id, confirmation_url, status
                """,
                telegram_id,
                package_key,
                lessons,
                amount_minor,
                provider_payment_id,
                confirmation_url,
            )
        return LessonPayment.from_record(record)

    async def get_lesson_payment(
        self,
        payment_id: int,
        telegram_id: int,
    ) -> Optional[LessonPayment]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                SELECT id, telegram_id, package_key, lessons, amount_minor,
                       provider_payment_id, confirmation_url, status
                FROM lesson_payments
                WHERE id = $1 AND telegram_id = $2
                """,
                payment_id,
                telegram_id,
            )
        return LessonPayment.from_record(record) if record is not None else None

    async def complete_lesson_payment(
        self,
        payment_id: int,
        telegram_id: int,
    ) -> bool:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                record = await connection.fetchrow(
                    """
                    UPDATE lesson_payments
                    SET status = 'succeeded', completed_at = NOW()
                    WHERE id = $1 AND telegram_id = $2 AND status = 'pending'
                    RETURNING lessons
                    """,
                    payment_id,
                    telegram_id,
                )
                if record is None:
                    return False
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET lesson_credits = lesson_credits + $2
                    WHERE telegram_id = $1
                    """,
                    telegram_id,
                    record["lessons"],
                )
        logger.info(
            "Lesson payment completed payment_id=%s telegram_id=%s lessons=%s",
            payment_id,
            telegram_id,
            record["lessons"],
        )
        return True

    async def cancel_lesson_payment(self, payment_id: int, telegram_id: int) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE lesson_payments
                SET status = 'canceled'
                WHERE id = $1 AND telegram_id = $2 AND status = 'pending'
                """,
                payment_id,
                telegram_id,
            )

    async def get_lesson_credits(self, telegram_id: int) -> int:
        async with self._pool.acquire() as connection:
            credits = await connection.fetchval(
                "SELECT lesson_credits FROM bot_users WHERE telegram_id = $1",
                telegram_id,
            )
        if credits is None:
            raise LookupError("Профиль не найден для Telegram ID {}".format(telegram_id))
        return credits

    async def close(self) -> None:
        await self._pool.close()
        logger.info("PostgreSQL connection pool closed")

    async def get_or_create_profile(
        self,
        telegram_id: int,
        user_name: str,
        is_admin: bool,
    ) -> UserProfile:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                INSERT INTO bot_users (telegram_id, user_name, is_admin)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_id) DO UPDATE
                    SET is_admin = bot_users.is_admin,
                        last_seen_at = NOW()
                RETURNING telegram_id, phone, user_name, registered_at, is_admin,
                          lesson_credits
                """,
                telegram_id,
                user_name,
                is_admin,
            )
        logger.info("Loaded profile telegram_id=%s", telegram_id)
        return UserProfile.from_record(record)

    async def update_phone(self, telegram_id: int, phone: str) -> None:
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                "UPDATE bot_users SET phone = $2 WHERE telegram_id = $1",
                telegram_id,
                phone,
            )
        self._require_updated(result, telegram_id)
        logger.info("Updated profile phone telegram_id=%s", telegram_id)

    async def update_user_name(self, telegram_id: int, user_name: str) -> None:
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                "UPDATE bot_users SET user_name = $2 WHERE telegram_id = $1",
                telegram_id,
                user_name,
            )
        self._require_updated(result, telegram_id)
        logger.info("Updated profile name telegram_id=%s", telegram_id)

    async def search_profiles(
        self,
        query: str,
        limit: int = 20,
    ) -> Sequence[UserProfile]:
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > 100:
            raise ValueError("Поисковый запрос должен содержать от 1 до 100 символов")
        if not 1 <= limit <= 100:
            raise ValueError("Количество профилей должно быть от 1 до 100")

        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT telegram_id, phone, user_name, registered_at, is_admin,
                       lesson_credits
                FROM bot_users
                WHERE telegram_id::TEXT = $1
                   OR user_name ILIKE $2
                   OR phone ILIKE $2
                ORDER BY registered_at DESC
                LIMIT $3
                """,
                normalized_query,
                "%{}%".format(normalized_query),
                limit,
            )
        logger.info("Searched profiles query_length=%s count=%s", len(normalized_query), len(records))
        return [UserProfile.from_record(record) for record in records]

    async def get_profile(self, telegram_id: int) -> Optional[UserProfile]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                SELECT telegram_id, phone, user_name, registered_at, is_admin,
                       lesson_credits
                FROM bot_users
                WHERE telegram_id = $1
                """,
                telegram_id,
            )
        return UserProfile.from_record(record) if record is not None else None

    async def create_lesson_request(
        self,
        telegram_id: int,
        kind: str,
        details: str,
    ) -> LessonRequest:
        if kind not in {"booking", "purchase"}:
            raise ValueError("Неизвестный тип заявки")

        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                INSERT INTO lesson_requests (telegram_id, kind, details)
                VALUES ($1, $2, $3)
                RETURNING id, telegram_id, kind, details, status, created_at
                """,
                telegram_id,
                kind,
                details,
            )
        logger.info(
            "Created lesson request id=%s telegram_id=%s kind=%s",
            record["id"],
            telegram_id,
            kind,
        )
        return LessonRequest.from_record(record)

    async def list_pending_requests(self, limit: int = 20) -> Sequence[LessonRequest]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество заявок должно быть от 1 до 100")

        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT id, telegram_id, kind, details, status, created_at
                FROM lesson_requests
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
        logger.info("Loaded %s pending requests", len(records))
        return [LessonRequest.from_record(record) for record in records]

    async def complete_request(self, request_id: int) -> bool:
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE lesson_requests
                SET status = 'completed'
                WHERE id = $1 AND status = 'pending'
                """,
                request_id,
            )
        completed = result == "UPDATE 1"
        logger.info("Completed request id=%s success=%s", request_id, completed)
        return completed

    @staticmethod
    def _require_updated(result: str, telegram_id: int) -> None:
        if result != "UPDATE 1":
            raise LookupError("Профиль не найден для Telegram ID {}".format(telegram_id))


def is_database_configured(database_url: str) -> bool:
    if not database_url:
        return False

    parsed_url = urlparse(database_url)
    hostname = parsed_url.hostname
    if not hostname or not parsed_url.scheme.startswith("postgres"):
        return False
    return hostname != "example.com" and not hostname.endswith(
        (".example.com", ".example.test")
    )


class InMemoryRepository:
    """Temporary repository used only when PostgreSQL is not configured."""

    supports_durable_payments = False

    def __init__(self) -> None:
        self._profiles: Dict[int, UserProfile] = {}
        self._requests: Dict[int, LessonRequest] = {}
        self._payments: Dict[int, LessonPayment] = {}
        self._last_seen: Dict[int, datetime] = {}
        self._next_request_id = 1
        self._next_payment_id = 1

    async def initialize(self) -> None:
        logger.warning("Using in-memory storage; data will be lost at shutdown")

    async def close(self) -> None:
        logger.info("In-memory storage closed")

    async def health_check(self) -> DatabaseHealth:
        return DatabaseHealth(
            backend="memory",
            pool_size=0,
            idle_connections=0,
        )

    async def get_or_create_profile(
        self,
        telegram_id: int,
        user_name: str,
        is_admin: bool,
    ) -> UserProfile:
        profile = self._profiles.get(telegram_id)
        if profile is None:
            profile = UserProfile(
                telegram_id=telegram_id,
                phone=None,
                user_name=user_name,
                registered_at=datetime.now(timezone.utc),
                is_admin=is_admin,
            )
        else:
            profile = UserProfile(
                telegram_id=profile.telegram_id,
                phone=profile.phone,
                user_name=profile.user_name,
                registered_at=profile.registered_at,
                is_admin=profile.is_admin,
                lesson_credits=profile.lesson_credits,
            )
        self._profiles[telegram_id] = profile
        self._last_seen[telegram_id] = datetime.now(timezone.utc)
        return profile

    async def record_activity(self, telegram_id: int) -> None:
        if telegram_id in self._profiles:
            self._last_seen[telegram_id] = datetime.now(timezone.utc)

    async def get_user_statistics(self, online_since: datetime) -> UserStatistics:
        total_users = len(self._profiles)
        online_users = sum(
            last_seen >= online_since
            for last_seen in self._last_seen.values()
        )
        return UserStatistics(total_users, online_users)

    async def update_phone(self, telegram_id: int, phone: str) -> None:
        profile = self._get_profile(telegram_id)
        self._profiles[telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits,
        )

    async def update_user_name(self, telegram_id: int, user_name: str) -> None:
        profile = self._get_profile(telegram_id)
        self._profiles[telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits,
        )

    async def create_lesson_payment(
        self,
        telegram_id: int,
        package_key: str,
        lessons: int,
        amount_minor: int,
        provider_payment_id: str,
        confirmation_url: str,
    ) -> LessonPayment:
        if telegram_id not in self._profiles:
            raise LookupError("Сначала создайте профиль командой /start")
        payment = LessonPayment(
            id=self._next_payment_id,
            telegram_id=telegram_id,
            package_key=package_key,
            lessons=lessons,
            amount_minor=amount_minor,
            provider_payment_id=provider_payment_id,
            confirmation_url=confirmation_url,
            status="pending",
        )
        self._payments[payment.id] = payment
        self._next_payment_id += 1
        return payment

    async def get_lesson_payment(
        self,
        payment_id: int,
        telegram_id: int,
    ) -> Optional[LessonPayment]:
        payment = self._payments.get(payment_id)
        if payment is None or payment.telegram_id != telegram_id:
            return None
        return payment

    async def complete_lesson_payment(
        self,
        payment_id: int,
        telegram_id: int,
    ) -> bool:
        payment = await self.get_lesson_payment(payment_id, telegram_id)
        if payment is None or payment.status != "pending":
            return False
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="succeeded",
        )
        profile = self._get_profile(telegram_id)
        self._profiles[telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits + payment.lessons,
        )
        return True

    async def cancel_lesson_payment(self, payment_id: int, telegram_id: int) -> None:
        payment = await self.get_lesson_payment(payment_id, telegram_id)
        if payment is None or payment.status != "pending":
            return
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="canceled",
        )

    async def get_lesson_credits(self, telegram_id: int) -> int:
        return self._get_profile(telegram_id).lesson_credits

    async def search_profiles(
        self,
        query: str,
        limit: int = 20,
    ) -> Sequence[UserProfile]:
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > 100:
            raise ValueError("Поисковый запрос должен содержать от 1 до 100 символов")
        if not 1 <= limit <= 100:
            raise ValueError("Количество профилей должно быть от 1 до 100")

        lowered_query = normalized_query.casefold()
        profiles = [
            profile
            for profile in self._profiles.values()
            if normalized_query == str(profile.telegram_id)
            or lowered_query in profile.user_name.casefold()
            or lowered_query in (profile.phone or "").casefold()
        ]
        profiles.sort(key=lambda profile: profile.registered_at, reverse=True)
        return profiles[:limit]

    async def get_profile(self, telegram_id: int) -> Optional[UserProfile]:
        return self._profiles.get(telegram_id)

    async def create_lesson_request(
        self,
        telegram_id: int,
        kind: str,
        details: str,
    ) -> LessonRequest:
        if telegram_id not in self._profiles:
            raise LookupError("Сначала создайте профиль командой /start")
        if kind not in {"booking", "purchase"}:
            raise ValueError("Неизвестный тип заявки")
        request = LessonRequest(
            id=self._next_request_id,
            telegram_id=telegram_id,
            kind=kind,
            details=details,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        self._requests[request.id] = request
        self._next_request_id += 1
        return request

    async def list_pending_requests(self, limit: int = 20) -> Sequence[LessonRequest]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество заявок должно быть от 1 до 100")
        requests = [
            request
            for request in self._requests.values()
            if request.status == "pending"
        ]
        requests.sort(key=lambda request: request.created_at, reverse=True)
        return requests[:limit]

    async def complete_request(self, request_id: int) -> bool:
        request = self._requests.get(request_id)
        if request is None or request.status != "pending":
            return False
        self._requests[request_id] = LessonRequest(
            id=request.id,
            telegram_id=request.telegram_id,
            kind=request.kind,
            details=request.details,
            status="completed",
            created_at=request.created_at,
        )
        return True

    def _get_profile(self, telegram_id: int) -> UserProfile:
        profile = self._profiles.get(telegram_id)
        if profile is None:
            raise LookupError("Профиль не найден для Telegram ID {}".format(telegram_id))
        return profile
