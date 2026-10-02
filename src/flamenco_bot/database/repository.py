import errno
import logging
import ipaddress
import socket
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

import asyncpg


logger = logging.getLogger("bot.database")
MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"
MIGRATION_LOCK_ID = 715_203_401
CLASS_KEYS = {"beginner", "intermediate", "individual"}
MAX_SUPPORT_MESSAGE_LENGTH = 2000


def _validate_slot(class_key: str, starts_at: datetime, capacity: int) -> None:
    if class_key not in CLASS_KEYS:
        raise ValueError("Неизвестный формат занятия")
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError("Время слота должно содержать часовой пояс")
    if starts_at <= datetime.now(timezone.utc):
        raise ValueError("Слот должен быть запланирован в будущем")
    if not 1 <= capacity <= 100:
        raise ValueError("Вместимость слота должна быть от 1 до 100")


def _validate_support_body(body: str) -> str:
    normalized = body.strip()
    if not normalized or len(normalized) > MAX_SUPPORT_MESSAGE_LENGTH:
        raise ValueError("Сообщение должно содержать от 1 до 2000 символов")
    return normalized


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
class ClassSlot:
    id: int
    class_key: str
    starts_at: datetime
    capacity: int
    booked_count: int
    status: str = "open"

    @property
    def remaining(self) -> int:
        return max(0, self.capacity - self.booked_count)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ClassSlot":
        return cls(
            id=record["id"],
            class_key=record["class_key"],
            starts_at=record["starts_at"],
            capacity=record["capacity"],
            booked_count=record["booked_count"],
            status=record["status"],
        )


@dataclass(frozen=True)
class ClassBooking:
    id: int
    slot_id: int
    telegram_id: int
    starts_at: datetime
    class_key: str
    already_booked: bool = False


@dataclass(frozen=True)
class UserBooking:
    """Запись участника на занятие вместе со статусом брони и слота.

    В отличие от ``ClassBooking`` (результат одного вызова ``book_class_slot``)
    используется для списков "мои занятия": несёт и статус брони
    (confirmed/cancelled), и статус самого слота (open/closed).
    """

    id: int
    slot_id: int
    class_key: str
    starts_at: datetime
    booking_status: str
    slot_status: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "UserBooking":
        return cls(
            id=record["id"],
            slot_id=record["slot_id"],
            class_key=record["class_key"],
            starts_at=record["starts_at"],
            booking_status=record["booking_status"],
            slot_status=record["slot_status"],
        )


@dataclass(frozen=True)
class SupportTicket:
    id: int
    telegram_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    last_message: str = ""


@dataclass(frozen=True)
class SupportMessage:
    ticket_id: int
    telegram_id: int
    sender_role: str
    body: str


class SlotUnavailableError(RuntimeError):
    """Raised when a class slot is closed, full, or no longer in the future."""


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
    package_title: str = "Пакет занятий"
    refund_idempotence_key: Optional[uuid.UUID] = None
    provider_refund_id: Optional[str] = None
    refund_reason: Optional[str] = None

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
            package_title=record.get("package_title", "Пакет занятий"),
            refund_idempotence_key=record.get("refund_idempotence_key"),
            provider_refund_id=record.get("provider_refund_id"),
            refund_reason=record.get("refund_reason"),
        )


@dataclass(frozen=True)
class LessonPaymentAttempt:
    idempotence_key: uuid.UUID
    telegram_id: int
    package_key: str
    package_title: str
    lessons: int
    amount_minor: int
    status: str
    provider_payment_id: Optional[str] = None
    confirmation_url: Optional[str] = None

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "LessonPaymentAttempt":
        return cls(
            idempotence_key=record["idempotence_key"],
            telegram_id=record["telegram_id"],
            package_key=record["package_key"],
            package_title=record["package_title"],
            lessons=record["lessons"],
            amount_minor=record["amount_minor"],
            status=record["status"],
            provider_payment_id=record["provider_payment_id"],
            confirmation_url=record["confirmation_url"],
        )


@dataclass(frozen=True)
class LessonRefund:
    payment_id: int
    telegram_id: int
    provider_payment_id: str
    amount_minor: int
    lessons: int
    idempotence_key: uuid.UUID
    provider_refund_id: Optional[str]
    reason: str


class PaymentAttemptUnresolved(RuntimeError):
    """An ambiguous checkout must be reviewed instead of creating another charge."""


@dataclass(frozen=True)
class LessonPaymentHistoryItem:
    """Строка истории платежей пользователя (список, не детали для сверки).

    Отдельный тип от ``LessonPayment``: тот используется в checkout/сверке
    и не несёт ``created_at`` (не было нужно ни одному из существующих
    вызовов), здесь же дата — главное поле для отображения списка.
    """

    id: int
    package_key: str
    package_title: str
    lessons: int
    amount_minor: int
    status: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "LessonPaymentHistoryItem":
        return cls(
            id=record["id"],
            package_key=record["package_key"],
            package_title=record["package_title"],
            lessons=record["lessons"],
            amount_minor=record["amount_minor"],
            status=record["status"],
            created_at=record["created_at"],
        )


@dataclass(frozen=True)
class WebUserRecord:
    """Веб-аккаунт сайта: вход по email/паролю и/или привязанный Telegram.

    Не владеет бизнес-данными бота — только ссылается на telegram_id, под
    которым они хранятся в bot_users/lesson_*. password_hash не должен
    попадать за пределы слоя репозитория/сервиса авторизации.
    """

    id: int
    email: Optional[str]
    password_hash: Optional[str]
    telegram_id: Optional[int]
    display_name: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "WebUserRecord":
        return cls(
            id=record["id"],
            email=record["email"],
            password_hash=record["password_hash"],
            telegram_id=record["telegram_id"],
            display_name=record["display_name"],
            created_at=record["created_at"],
        )


class EmailAlreadyRegisteredError(ValueError):
    """На этот email уже зарегистрирован веб-аккаунт."""


class TelegramAlreadyLinkedError(ValueError):
    """Этот Telegram уже привязан к другому веб-аккаунту."""


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
                "Размер пула PostgreSQL должен удовлетворять 1 <= min_size <= max_size"
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
                    await connection.execute(migration.read_text(encoding="utf-8"))
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

    async def get_scheduled_restart(self) -> Optional[datetime]:
        async with self._pool.acquire() as connection:
            value = await connection.fetchval(
                "SELECT setting_value FROM bot_runtime_settings "
                "WHERE setting_key = 'scheduled_restart_at'"
            )
        return datetime.fromisoformat(value) if value is not None else None

    async def set_scheduled_restart(self, scheduled_at: datetime) -> None:
        if scheduled_at.tzinfo is None:
            raise ValueError("Время рестарта должно содержать часовой пояс")
        async with self._pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO bot_runtime_settings (setting_key, setting_value)
                VALUES ('scheduled_restart_at', $1)
                ON CONFLICT (setting_key)
                DO UPDATE SET setting_value = EXCLUDED.setting_value,
                              updated_at = NOW()
                """,
                scheduled_at.isoformat(),
            )
        logger.info("Persisted scheduled restart at=%s", scheduled_at.isoformat())

    async def clear_scheduled_restart(self) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM bot_runtime_settings "
                "WHERE setting_key = 'scheduled_restart_at'"
            )
        logger.info("Cleared persisted scheduled restart")

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

    async def begin_lesson_payment_attempt(
        self,
        telegram_id: int,
        package_key: str,
        package_title: str,
        lessons: int,
        amount_minor: int,
    ) -> LessonPaymentAttempt:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1::BIGINT::TEXT || ':' || $2::TEXT, 0)
                    )
                    """,
                    telegram_id,
                    package_key,
                )
                record = await connection.fetchrow(
                    """
                    SELECT idempotence_key, telegram_id, package_key, package_title,
                           lessons, amount_minor, status, provider_payment_id,
                           confirmation_url, created_at
                    FROM lesson_payment_attempts
                    WHERE telegram_id = $1 AND package_key = $2
                      AND status IN ('creating', 'pending')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    telegram_id,
                    package_key,
                )
                if record is not None:
                    if (
                        record["status"] == "creating"
                        and (
                            datetime.now(timezone.utc) - record["created_at"]
                        ).total_seconds()
                        > 23 * 60 * 60
                    ):
                        raise PaymentAttemptUnresolved(
                            "Неоднозначный платёж требует сверки с ЮKassa"
                        )
                    logger.info(
                        "Reusing lesson payment attempt telegram_id=%s "
                        "package=%s status=%s",
                        telegram_id,
                        package_key,
                        record["status"],
                    )
                    return LessonPaymentAttempt.from_record(record)

                legacy_payment_id = await connection.fetchval(
                    """
                    SELECT id
                    FROM lesson_payments
                    WHERE telegram_id = $1
                      AND package_key = $2
                      AND status = 'pending'
                      AND idempotence_key IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    telegram_id,
                    package_key,
                )
                if legacy_payment_id is not None:
                    raise PaymentAttemptUnresolved(
                        "Незавершённый платёж создан до включения безопасных повторов; "
                        "сначала сверьте его статус с ЮKassa"
                    )

                record = await connection.fetchrow(
                    """
                    INSERT INTO lesson_payment_attempts (
                        idempotence_key, telegram_id, package_key, package_title,
                        lessons, amount_minor
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING idempotence_key, telegram_id, package_key, package_title,
                              lessons, amount_minor, status, provider_payment_id,
                              confirmation_url
                    """,
                    uuid.uuid4(),
                    telegram_id,
                    package_key,
                    package_title,
                    lessons,
                    amount_minor,
                )
        logger.info(
            "Started lesson payment attempt telegram_id=%s package=%s",
            telegram_id,
            package_key,
        )
        return LessonPaymentAttempt.from_record(record)

    async def create_lesson_payment(
        self,
        telegram_id: int,
        package_key: str,
        package_title: str,
        lessons: int,
        amount_minor: int,
        provider_payment_id: str,
        confirmation_url: str,
        idempotence_key: uuid.UUID,
    ) -> LessonPayment:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                record = await connection.fetchrow(
                    """
                    INSERT INTO lesson_payments (
                        telegram_id, package_key, package_title, lessons, amount_minor,
                        provider_payment_id, confirmation_url, idempotence_key
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (idempotence_key) WHERE idempotence_key IS NOT NULL
                    DO UPDATE SET idempotence_key = EXCLUDED.idempotence_key
                    RETURNING id, telegram_id, package_key, package_title, lessons,
                              amount_minor, provider_payment_id, confirmation_url,
                              status, refund_idempotence_key, provider_refund_id,
                              refund_reason
                    """,
                    telegram_id,
                    package_key,
                    package_title,
                    lessons,
                    amount_minor,
                    provider_payment_id,
                    confirmation_url,
                    idempotence_key,
                )
                await connection.execute(
                    """
                    UPDATE lesson_payment_attempts
                    SET status = CASE
                            WHEN status IN ('completed', 'failed') THEN status
                            ELSE 'pending'
                        END,
                        provider_payment_id = $2,
                        confirmation_url = $3, updated_at = NOW()
                    WHERE idempotence_key = $1
                    """,
                    idempotence_key,
                    provider_payment_id,
                    confirmation_url,
                )
                await connection.execute(
                    """
                    INSERT INTO lesson_payment_events (payment_id, event_type)
                    VALUES ($1, 'created')
                    ON CONFLICT DO NOTHING
                    """,
                    record["id"],
                )
        logger.info(
            "Saved lesson payment payment_id=%s telegram_id=%s package=%s",
            record["id"],
            telegram_id,
            package_key,
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
                SELECT id, telegram_id, package_key, package_title, lessons,
                       amount_minor, provider_payment_id, confirmation_url, status,
                       refund_idempotence_key, provider_refund_id, refund_reason
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
                    INSERT INTO lesson_credit_ledger (
                        telegram_id, payment_id, entry_type, delta, reference_key
                    )
                    VALUES ($1, $2, 'purchase', $3, $4)
                    """,
                    telegram_id,
                    payment_id,
                    record["lessons"],
                    "payment:{}".format(payment_id),
                )
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET lesson_credits = lesson_credits + $2
                    WHERE telegram_id = $1
                    """,
                    telegram_id,
                    record["lessons"],
                )
                await connection.execute(
                    """
                    UPDATE lesson_payment_attempts
                    SET status = 'completed', updated_at = NOW()
                    WHERE idempotence_key = (
                        SELECT idempotence_key FROM lesson_payments WHERE id = $1
                    )
                    """,
                    payment_id,
                )
                await connection.execute(
                    "INSERT INTO lesson_payment_events (payment_id, event_type) "
                    "VALUES ($1, 'succeeded')",
                    payment_id,
                )
        logger.info(
            "Lesson payment completed payment_id=%s telegram_id=%s lessons=%s",
            payment_id,
            telegram_id,
            record["lessons"],
        )
        return True

    async def cancel_lesson_payment(self, payment_id: int, telegram_id: int) -> bool:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                payment = await connection.fetchrow(
                    """
                    UPDATE lesson_payments
                    SET status = 'canceled'
                    WHERE id = $1 AND telegram_id = $2 AND status = 'pending'
                    RETURNING idempotence_key
                    """,
                    payment_id,
                    telegram_id,
                )
                canceled = payment is not None
                if canceled:
                    await connection.execute(
                        """
                        UPDATE lesson_payment_attempts
                        SET status = 'failed', updated_at = NOW()
                        WHERE idempotence_key = $1 AND status = 'pending'
                        """,
                        payment["idempotence_key"],
                    )
                    await connection.execute(
                        "INSERT INTO lesson_payment_events (payment_id, event_type) "
                        "VALUES ($1, 'canceled')",
                        payment_id,
                    )
        logger.info(
            "Lesson payment cancellation recorded payment_id=%s "
            "telegram_id=%s updated=%s",
            payment_id,
            telegram_id,
            canceled,
        )
        return canceled

    async def prepare_lesson_refund(
        self,
        payment_id: int,
        admin_telegram_id: int,
        reason: str,
    ) -> Optional[LessonRefund]:
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 300:
            raise ValueError("Причина возврата должна содержать от 1 до 300 символов")

        async with self._pool.acquire() as connection:
            async with connection.transaction():
                payment = await connection.fetchrow(
                    """
                    SELECT id, telegram_id, provider_payment_id, amount_minor,
                           lessons, status, refund_idempotence_key,
                           provider_refund_id, refund_reason
                    FROM lesson_payments WHERE id = $1 FOR UPDATE
                    """,
                    payment_id,
                )
                if payment is None:
                    return None
                if payment["status"] == "refund_pending":
                    return LessonRefund(
                        payment_id=payment["id"],
                        telegram_id=payment["telegram_id"],
                        provider_payment_id=payment["provider_payment_id"],
                        amount_minor=payment["amount_minor"],
                        lessons=payment["lessons"],
                        idempotence_key=payment["refund_idempotence_key"],
                        provider_refund_id=payment["provider_refund_id"],
                        reason=payment["refund_reason"] or normalized_reason,
                    )
                if payment["status"] != "succeeded":
                    return None

                profile = await connection.fetchrow(
                    """
                    SELECT lesson_credits FROM bot_users
                    WHERE telegram_id = $1 FOR UPDATE
                    """,
                    payment["telegram_id"],
                )
                payment_credit_balance = await connection.fetchval(
                    """
                    SELECT COALESCE(SUM(delta), 0)
                    FROM lesson_credit_ledger
                    WHERE payment_id = $1
                      AND entry_type IN (
                          'purchase', 'lesson_use', 'refund_reservation',
                          'refund', 'refund_release'
                      )
                    """,
                    payment_id,
                )
                if (
                    profile is None
                    or profile["lesson_credits"] < payment["lessons"]
                    or payment_credit_balance < payment["lessons"]
                ):
                    raise ValueError(
                        "Недостаточно неиспользованных занятий для возврата"
                    )

                refund_key = uuid.uuid4()
                await connection.execute(
                    "UPDATE bot_users SET lesson_credits = lesson_credits - $2 "
                    "WHERE telegram_id = $1",
                    payment["telegram_id"],
                    payment["lessons"],
                )
                await connection.execute(
                    """
                    INSERT INTO lesson_credit_ledger (
                        telegram_id, payment_id, entry_type, delta, reference_key
                    )
                    VALUES ($1, $2, 'refund_reservation', $3, $4)
                    """,
                    payment["telegram_id"],
                    payment_id,
                    -payment["lessons"],
                    "refund-reservation:{}:{}".format(payment_id, refund_key),
                )
                await connection.execute(
                    """
                    UPDATE lesson_payments
                    SET status = 'refund_pending', refund_idempotence_key = $2,
                        refund_reason = $3
                    WHERE id = $1
                    """,
                    payment_id,
                    refund_key,
                    normalized_reason,
                )
                await connection.execute(
                    """
                    INSERT INTO lesson_payment_events (
                        payment_id, event_type, actor_telegram_id, reason
                    )
                    VALUES ($1, 'refund_requested', $2, $3)
                    """,
                    payment_id,
                    admin_telegram_id,
                    normalized_reason,
                )
        logger.warning(
            "Lesson refund reserved payment_id=%s admin_id=%s",
            payment_id,
            admin_telegram_id,
        )
        return LessonRefund(
            payment_id=payment["id"],
            telegram_id=payment["telegram_id"],
            provider_payment_id=payment["provider_payment_id"],
            amount_minor=payment["amount_minor"],
            lessons=payment["lessons"],
            idempotence_key=refund_key,
            provider_refund_id=None,
            reason=normalized_reason,
        )

    async def record_provider_refund(
        self,
        payment_id: int,
        provider_refund_id: str,
    ) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE lesson_payments SET provider_refund_id = $2
                WHERE id = $1 AND status = 'refund_pending'
                """,
                payment_id,
                provider_refund_id,
            )
        logger.info("Recorded provider refund payment_id=%s", payment_id)

    async def complete_lesson_refund(self, payment_id: int) -> bool:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                payment = await connection.fetchrow(
                    """
                    UPDATE lesson_payments
                    SET status = 'refunded', refunded_at = NOW()
                    WHERE id = $1 AND status = 'refund_pending'
                    RETURNING telegram_id
                    """,
                    payment_id,
                )
                if payment is None:
                    return False
                await connection.execute(
                    """
                    UPDATE lesson_credit_ledger
                    SET entry_type = 'refund'
                    WHERE payment_id = $1 AND entry_type = 'refund_reservation'
                    """,
                    payment_id,
                )
                await connection.execute(
                    "INSERT INTO lesson_payment_events (payment_id, event_type) "
                    "VALUES ($1, 'refunded')",
                    payment_id,
                )
        logger.warning("Lesson payment refunded payment_id=%s", payment_id)
        return True

    async def release_lesson_refund(self, payment_id: int) -> bool:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                payment = await connection.fetchrow(
                    """
                    SELECT telegram_id, lessons, provider_refund_id
                    FROM lesson_payments
                    WHERE id = $1 AND status = 'refund_pending'
                    FOR UPDATE
                    """,
                    payment_id,
                )
                if payment is None:
                    return False
                await connection.execute(
                    """
                    UPDATE lesson_payments
                    SET status = 'succeeded', refund_idempotence_key = NULL,
                        provider_refund_id = NULL
                    WHERE id = $1 AND status = 'refund_pending'
                    """,
                    payment_id,
                )
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET lesson_credits = lesson_credits + $2
                    WHERE telegram_id = $1
                    """,
                    payment["telegram_id"],
                    payment["lessons"],
                )
                await connection.execute(
                    """
                    INSERT INTO lesson_credit_ledger (
                        telegram_id, payment_id, entry_type, delta, reference_key
                    )
                    VALUES ($1, $2, 'refund_release', $3, $4)
                    """,
                    payment["telegram_id"],
                    payment_id,
                    payment["lessons"],
                    "refund-release:{}:{}".format(payment_id, uuid.uuid4()),
                )
                await connection.execute(
                    """
                    INSERT INTO lesson_payment_events (
                        payment_id, event_type, reason, provider_refund_id
                    )
                    VALUES ($1, 'refund_failed', 'Provider canceled refund', $2)
                    """,
                    payment_id,
                    payment["provider_refund_id"],
                )
        logger.warning("Lesson refund reservation released payment_id=%s", payment_id)
        return True

    async def get_lesson_credits(self, telegram_id: int) -> int:
        async with self._pool.acquire() as connection:
            credits = await connection.fetchval(
                "SELECT lesson_credits FROM bot_users WHERE telegram_id = $1",
                telegram_id,
            )
        if credits is None:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )
        return credits

    async def list_lesson_payments_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 20,
    ) -> Sequence[LessonPaymentHistoryItem]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество платежей должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT id, package_key, package_title, lessons, amount_minor,
                       status, created_at
                FROM lesson_payments
                WHERE telegram_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                telegram_id,
                limit,
            )
        return [LessonPaymentHistoryItem.from_record(record) for record in records]

    async def create_web_user(
        self,
        email: str,
        password_hash: str,
        display_name: str,
    ) -> WebUserRecord:
        async with self._pool.acquire() as connection:
            try:
                record = await connection.fetchrow(
                    """
                    INSERT INTO users (email, password_hash, display_name)
                    VALUES ($1, $2, $3)
                    RETURNING id, email, password_hash, telegram_id, display_name,
                              created_at
                    """,
                    email,
                    password_hash,
                    display_name,
                )
            except asyncpg.UniqueViolationError as error:
                raise EmailAlreadyRegisteredError(
                    "Этот email уже зарегистрирован"
                ) from error
        logger.info("Created web user id=%s", record["id"])
        return WebUserRecord.from_record(record)

    async def get_or_create_web_user_from_telegram(
        self,
        telegram_id: int,
        display_name: str,
    ) -> WebUserRecord:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                INSERT INTO users (telegram_id, display_name)
                VALUES ($1, $2)
                ON CONFLICT (telegram_id) DO NOTHING
                RETURNING id, email, password_hash, telegram_id, display_name,
                          created_at
                """,
                telegram_id,
                display_name,
            )
            if record is None:
                record = await connection.fetchrow(
                    """
                    SELECT id, email, password_hash, telegram_id, display_name,
                           created_at
                    FROM users WHERE telegram_id = $1
                    """,
                    telegram_id,
                )
        return WebUserRecord.from_record(record)

    async def get_web_user_by_id(self, user_id: int) -> Optional[WebUserRecord]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                SELECT id, email, password_hash, telegram_id, display_name, created_at
                FROM users WHERE id = $1
                """,
                user_id,
            )
        return WebUserRecord.from_record(record) if record is not None else None

    async def get_web_user_by_email(self, email: str) -> Optional[WebUserRecord]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                SELECT id, email, password_hash, telegram_id, display_name, created_at
                FROM users WHERE LOWER(email) = LOWER($1)
                """,
                email,
            )
        return WebUserRecord.from_record(record) if record is not None else None

    async def get_web_user_by_telegram_id(
        self,
        telegram_id: int,
    ) -> Optional[WebUserRecord]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                SELECT id, email, password_hash, telegram_id, display_name, created_at
                FROM users WHERE telegram_id = $1
                """,
                telegram_id,
            )
        return WebUserRecord.from_record(record) if record is not None else None

    async def set_web_user_telegram_id(
        self,
        user_id: int,
        telegram_id: Optional[int],
    ) -> bool:
        async with self._pool.acquire() as connection:
            try:
                result = await connection.execute(
                    "UPDATE users SET telegram_id = $2, updated_at = NOW() "
                    "WHERE id = $1",
                    user_id,
                    telegram_id,
                )
            except asyncpg.UniqueViolationError as error:
                raise TelegramAlreadyLinkedError(
                    "Этот Telegram уже привязан к другому аккаунту"
                ) from error
        logger.info(
            "Updated web user telegram link user_id=%s linked=%s",
            user_id,
            telegram_id is not None,
        )
        return result == "UPDATE 1"

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
        logger.info(
            "Searched profiles query_length=%s count=%s",
            len(normalized_query),
            len(records),
        )
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

    async def create_class_slot(
        self,
        class_key: str,
        starts_at: datetime,
        capacity: int,
        admin_telegram_id: int,
    ) -> ClassSlot:
        _validate_slot(class_key, starts_at, capacity)
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                INSERT INTO lesson_slots (class_key, starts_at, capacity, created_by)
                VALUES ($1, $2, $3, $4)
                RETURNING id, class_key, starts_at, capacity, 0 AS booked_count,
                          status
                """,
                class_key,
                starts_at,
                capacity,
                admin_telegram_id,
            )
        logger.info("Created class slot id=%s class=%s", record["id"], class_key)
        return ClassSlot.from_record(record)

    async def list_class_slots(
        self,
        class_key: Optional[str] = None,
        limit: int = 100,
    ) -> Sequence[ClassSlot]:
        if class_key is not None and class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT slot.id, slot.class_key, slot.starts_at, slot.capacity,
                       slot.status,
                       COUNT(booking.id) FILTER (
                           WHERE booking.status = 'confirmed'
                       )::INTEGER AS booked_count
                FROM lesson_slots AS slot
                LEFT JOIN lesson_bookings AS booking ON booking.slot_id = slot.id
                WHERE slot.starts_at > NOW()
                  AND ($1::TEXT IS NULL OR slot.class_key = $1)
                GROUP BY slot.id
                ORDER BY slot.starts_at
                LIMIT $2
                """,
                class_key,
                limit,
            )
        return [ClassSlot.from_record(record) for record in records]

    async def list_available_class_slots(
        self,
        class_key: str,
        limit: int = 20,
    ) -> Sequence[ClassSlot]:
        if class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT slot.id, slot.class_key, slot.starts_at, slot.capacity,
                       slot.status,
                       COUNT(booking.id) FILTER (
                           WHERE booking.status = 'confirmed'
                       )::INTEGER AS booked_count
                FROM lesson_slots AS slot
                LEFT JOIN lesson_bookings AS booking ON booking.slot_id = slot.id
                WHERE slot.class_key = $1
                  AND slot.status = 'open'
                  AND slot.starts_at > NOW()
                GROUP BY slot.id
                HAVING COUNT(booking.id) FILTER (
                    WHERE booking.status = 'confirmed'
                ) < slot.capacity
                ORDER BY slot.starts_at
                LIMIT $2
                """,
                class_key,
                limit,
            )
        return [ClassSlot.from_record(record) for record in records]

    async def book_class_slot(
        self,
        slot_id: int,
        telegram_id: int,
    ) -> ClassBooking:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                slot = await connection.fetchrow(
                    """
                    SELECT id, class_key, starts_at, capacity, status
                    FROM lesson_slots
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    slot_id,
                )
                if (
                    slot is None
                    or slot["status"] != "open"
                    or slot["starts_at"] <= datetime.now(timezone.utc)
                ):
                    raise SlotUnavailableError("Слот закрыт или уже недоступен")

                existing = await connection.fetchrow(
                    """
                    SELECT id, status FROM lesson_bookings
                    WHERE slot_id = $1 AND telegram_id = $2
                    """,
                    slot_id,
                    telegram_id,
                )
                if existing is not None and existing["status"] == "confirmed":
                    return ClassBooking(
                        id=existing["id"],
                        slot_id=slot_id,
                        telegram_id=telegram_id,
                        starts_at=slot["starts_at"],
                        class_key=slot["class_key"],
                        already_booked=True,
                    )

                booked_count = await connection.fetchval(
                    """
                    SELECT COUNT(*) FROM lesson_bookings
                    WHERE slot_id = $1 AND status = 'confirmed'
                    """,
                    slot_id,
                )
                if booked_count >= slot["capacity"]:
                    raise SlotUnavailableError("На это занятие уже нет свободных мест")

                booking = await connection.fetchrow(
                    """
                    INSERT INTO lesson_bookings (slot_id, telegram_id)
                    VALUES ($1, $2)
                    ON CONFLICT (slot_id, telegram_id)
                    DO UPDATE SET status = 'confirmed', booked_at = NOW(),
                                  updated_at = NOW()
                    WHERE lesson_bookings.status = 'cancelled'
                    RETURNING id
                    """,
                    slot_id,
                    telegram_id,
                )
                if booking is None:
                    raise SlotUnavailableError("Не удалось подтвердить место")
        logger.info(
            "Confirmed class booking slot_id=%s telegram_id=%s",
            slot_id,
            telegram_id,
        )
        return ClassBooking(
            id=booking["id"],
            slot_id=slot_id,
            telegram_id=telegram_id,
            starts_at=slot["starts_at"],
            class_key=slot["class_key"],
        )

    async def list_bookings_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 50,
    ) -> Sequence[UserBooking]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество записей должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT booking.id, booking.slot_id, slot.class_key,
                       slot.starts_at, booking.status AS booking_status,
                       slot.status AS slot_status
                FROM lesson_bookings AS booking
                JOIN lesson_slots AS slot ON slot.id = booking.slot_id
                WHERE booking.telegram_id = $1
                ORDER BY slot.starts_at DESC
                LIMIT $2
                """,
                telegram_id,
                limit,
            )
        return [UserBooking.from_record(record) for record in records]

    async def update_class_slot_capacity(self, slot_id: int, capacity: int) -> bool:
        if not 1 <= capacity <= 100:
            raise ValueError("Вместимость слота должна быть от 1 до 100")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                slot = await connection.fetchrow(
                    "SELECT id FROM lesson_slots WHERE id = $1 FOR UPDATE",
                    slot_id,
                )
                if slot is None:
                    return False
                booked_count = await connection.fetchval(
                    """
                    SELECT COUNT(*) FROM lesson_bookings
                    WHERE slot_id = $1 AND status = 'confirmed'
                    """,
                    slot_id,
                )
                if capacity < booked_count:
                    raise ValueError(
                        "Нельзя установить вместимость ниже числа "
                        "подтверждённых записей"
                    )
                await connection.execute(
                    """
                    UPDATE lesson_slots
                    SET capacity = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    slot_id,
                    capacity,
                )
        return True

    async def close_class_slot(self, slot_id: int) -> bool:
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE lesson_slots SET status = 'closed', updated_at = NOW()
                WHERE id = $1 AND status = 'open'
                """,
                slot_id,
            )
        return result == "UPDATE 1"

    async def list_admin_ids(self) -> Sequence[int]:
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                "SELECT telegram_id FROM bot_users WHERE is_admin = TRUE "
                "ORDER BY telegram_id"
            )
        return [record["telegram_id"] for record in records]

    async def create_support_message(
        self,
        telegram_id: int,
        body: str,
    ) -> tuple[int, bool]:
        normalized = _validate_support_body(body)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended($1::BIGINT::TEXT, 0)
                    )
                    """,
                    telegram_id,
                )
                ticket_id = await connection.fetchval(
                    """
                    SELECT id FROM support_tickets
                    WHERE telegram_id = $1 AND status = 'open'
                    ORDER BY id DESC LIMIT 1
                    FOR UPDATE
                    """,
                    telegram_id,
                )
                created = ticket_id is None
                if created:
                    ticket_id = await connection.fetchval(
                        """
                        INSERT INTO support_tickets (telegram_id)
                        VALUES ($1) RETURNING id
                        """,
                        telegram_id,
                    )
                await connection.execute(
                    """
                    INSERT INTO support_messages (
                        ticket_id, sender_telegram_id, sender_role, body
                    )
                    VALUES ($1, $2, 'user', $3)
                    """,
                    ticket_id,
                    telegram_id,
                    normalized,
                )
                await connection.execute(
                    "UPDATE support_tickets SET updated_at = NOW() WHERE id = $1",
                    ticket_id,
                )
        logger.info(
            "Stored support message ticket_id=%s telegram_id=%s new_ticket=%s",
            ticket_id,
            telegram_id,
            created,
        )
        return ticket_id, created

    async def reply_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        body: str,
    ) -> Optional[int]:
        normalized = _validate_support_body(body)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                ticket = await connection.fetchrow(
                    """
                    SELECT telegram_id FROM support_tickets
                    WHERE id = $1 AND status = 'open'
                    FOR UPDATE
                    """,
                    ticket_id,
                )
                if ticket is None:
                    return None
                await connection.execute(
                    """
                    INSERT INTO support_messages (
                        ticket_id, sender_telegram_id, sender_role, body
                    )
                    VALUES ($1, $2, 'admin', $3)
                    """,
                    ticket_id,
                    admin_telegram_id,
                    normalized,
                )
                await connection.execute(
                    "UPDATE support_tickets SET updated_at = NOW() WHERE id = $1",
                    ticket_id,
                )
        return ticket["telegram_id"]

    async def list_open_support_tickets(
        self,
        limit: int = 20,
    ) -> Sequence[SupportTicket]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество обращений должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT ticket.id, ticket.telegram_id, ticket.status,
                       ticket.created_at, ticket.updated_at,
                       message.body AS last_message
                FROM support_tickets AS ticket
                LEFT JOIN LATERAL (
                    SELECT body FROM support_messages
                    WHERE ticket_id = ticket.id
                    ORDER BY created_at DESC, id DESC LIMIT 1
                ) AS message ON TRUE
                WHERE ticket.status = 'open'
                ORDER BY ticket.updated_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [
            SupportTicket(
                id=record["id"],
                telegram_id=record["telegram_id"],
                status=record["status"],
                created_at=record["created_at"],
                updated_at=record["updated_at"],
                last_message=record["last_message"] or "",
            )
            for record in records
        ]

    async def list_support_tickets_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 20,
    ) -> Sequence[SupportTicket]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество обращений должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT ticket.id, ticket.telegram_id, ticket.status,
                       ticket.created_at, ticket.updated_at,
                       message.body AS last_message
                FROM support_tickets AS ticket
                LEFT JOIN LATERAL (
                    SELECT body FROM support_messages
                    WHERE ticket_id = ticket.id
                    ORDER BY created_at DESC, id DESC LIMIT 1
                ) AS message ON TRUE
                WHERE ticket.telegram_id = $1
                ORDER BY ticket.updated_at DESC
                LIMIT $2
                """,
                telegram_id,
                limit,
            )
        return [
            SupportTicket(
                id=record["id"],
                telegram_id=record["telegram_id"],
                status=record["status"],
                created_at=record["created_at"],
                updated_at=record["updated_at"],
                last_message=record["last_message"] or "",
            )
            for record in records
        ]

    async def close_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
    ) -> Optional[int]:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                ticket = await connection.fetchrow(
                    """
                    UPDATE support_tickets
                    SET status = 'closed', updated_at = NOW()
                    WHERE id = $1 AND status = 'open'
                    RETURNING telegram_id
                    """,
                    ticket_id,
                )
                if ticket is None:
                    return None
                await connection.execute(
                    """
                    INSERT INTO support_messages (
                        ticket_id, sender_telegram_id, sender_role, body
                    )
                    VALUES ($1, $2, 'admin', 'Обращение закрыто.')
                    """,
                    ticket_id,
                    admin_telegram_id,
                )
        return ticket["telegram_id"]

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
            async with connection.transaction():
                request = await connection.fetchrow(
                    """
                    SELECT telegram_id, kind
                    FROM lesson_requests
                    WHERE id = $1 AND status = 'pending'
                    FOR UPDATE
                    """,
                    request_id,
                )
                if request is None:
                    return False
                await connection.execute(
                    "UPDATE lesson_requests SET status = 'completed' WHERE id = $1",
                    request_id,
                )
                if request["kind"] == "booking":
                    profile = await connection.fetchrow(
                        """
                        UPDATE bot_users
                        SET lesson_credits = lesson_credits - 1
                        WHERE telegram_id = $1 AND lesson_credits > 0
                        RETURNING lesson_credits
                        """,
                        request["telegram_id"],
                    )
                    if profile is not None:
                        current_credits = profile["lesson_credits"] + 1
                        allocated_credits = await connection.fetchval(
                            """
                            SELECT COALESCE(SUM(remaining), 0)
                            FROM (
                                SELECT SUM(ledger.delta) AS remaining
                                FROM lesson_payments AS payment
                                JOIN lesson_credit_ledger AS ledger
                                  ON ledger.payment_id = payment.id
                                WHERE payment.telegram_id = $1
                                  AND payment.status = 'succeeded'
                                GROUP BY payment.id
                                HAVING SUM(ledger.delta) > 0
                            ) AS allocated
                            """,
                            request["telegram_id"],
                        )
                        payment_credit = None
                        if current_credits <= allocated_credits:
                            payment_credit = await connection.fetchrow(
                                """
                                SELECT payment.id
                                FROM lesson_payments AS payment
                                JOIN lesson_credit_ledger AS ledger
                                  ON ledger.payment_id = payment.id
                                WHERE payment.telegram_id = $1
                                  AND payment.status = 'succeeded'
                                GROUP BY payment.id
                                HAVING SUM(ledger.delta) > 0
                                ORDER BY payment.id
                                LIMIT 1
                                """,
                                request["telegram_id"],
                            )
                        await connection.execute(
                            """
                            INSERT INTO lesson_credit_ledger (
                                telegram_id, entry_type, delta, reference_key
                            )
                            VALUES ($1, 'lesson_use', -1, $2)
                            """,
                            request["telegram_id"],
                            "request:{}".format(request_id),
                        )
                        if payment_credit is not None:
                            await connection.execute(
                                """
                                UPDATE lesson_credit_ledger
                                SET payment_id = $2
                                WHERE telegram_id = $1
                                  AND entry_type = 'lesson_use'
                                  AND reference_key = $3
                                """,
                                request["telegram_id"],
                                payment_credit["id"],
                                "request:{}".format(request_id),
                            )
                        logger.info(
                            "Debited lesson credit request_id=%s "
                            "telegram_id=%s remaining=%s",
                            request_id,
                            request["telegram_id"],
                            profile["lesson_credits"],
                        )
        completed = True
        logger.info("Completed request id=%s success=%s", request_id, completed)
        return completed

    @staticmethod
    def _require_updated(result: str, telegram_id: int) -> None:
        if result != "UPDATE 1":
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )


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
        # LessonPayment (используется в checkout/сверке) не несёт created_at —
        # отдельный словарь только для list_lesson_payments_for_telegram_id.
        self._payment_created_at: Dict[int, datetime] = {}
        self._payment_attempts: Dict[Tuple[int, str], LessonPaymentAttempt] = {}
        self._credit_ledger: list[Tuple[int, int, str, Optional[int]]] = []
        self._class_slots: Dict[int, ClassSlot] = {}
        self._class_bookings: Dict[Tuple[int, int], ClassBooking] = {}
        self._support_tickets: Dict[int, SupportTicket] = {}
        self._support_messages: Dict[int, list[SupportMessage]] = {}
        self._last_seen: Dict[int, datetime] = {}
        self._scheduled_restart_at: Optional[datetime] = None
        self._next_request_id = 1
        self._next_payment_id = 1
        self._next_slot_id = 1
        self._next_booking_id = 1
        self._next_support_ticket_id = 1
        self._web_users: Dict[int, WebUserRecord] = {}
        self._next_web_user_id = 1

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

    async def get_scheduled_restart(self) -> Optional[datetime]:
        return self._scheduled_restart_at

    async def set_scheduled_restart(self, scheduled_at: datetime) -> None:
        self._scheduled_restart_at = scheduled_at

    async def clear_scheduled_restart(self) -> None:
        self._scheduled_restart_at = None

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
            last_seen >= online_since for last_seen in self._last_seen.values()
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

    async def begin_lesson_payment_attempt(
        self,
        telegram_id: int,
        package_key: str,
        package_title: str,
        lessons: int,
        amount_minor: int,
    ) -> LessonPaymentAttempt:
        if telegram_id not in self._profiles:
            raise LookupError("Сначала создайте профиль командой /start")
        attempt_key = (telegram_id, package_key)
        existing = self._payment_attempts.get(attempt_key)
        if existing is not None and existing.status in {"creating", "pending"}:
            return existing
        attempt = LessonPaymentAttempt(
            idempotence_key=uuid.uuid4(),
            telegram_id=telegram_id,
            package_key=package_key,
            package_title=package_title,
            lessons=lessons,
            amount_minor=amount_minor,
            status="creating",
        )
        self._payment_attempts[attempt_key] = attempt
        return attempt

    async def create_lesson_payment(
        self,
        telegram_id: int,
        package_key: str,
        package_title: str,
        lessons: int,
        amount_minor: int,
        provider_payment_id: str,
        confirmation_url: str,
        idempotence_key: uuid.UUID,
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
            package_title=package_title,
        )
        existing = next(
            (
                item
                for item in self._payments.values()
                if item.provider_payment_id == provider_payment_id
            ),
            None,
        )
        if existing is not None:
            return existing
        self._payments[payment.id] = payment
        self._payment_created_at[payment.id] = datetime.now(timezone.utc)
        self._next_payment_id += 1
        self._payment_attempts[(telegram_id, package_key)] = LessonPaymentAttempt(
            idempotence_key=idempotence_key,
            telegram_id=telegram_id,
            package_key=package_key,
            package_title=package_title,
            lessons=lessons,
            amount_minor=amount_minor,
            status="pending",
            provider_payment_id=provider_payment_id,
            confirmation_url=confirmation_url,
        )
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
            package_title=payment.package_title,
        )
        attempt_key = (payment.telegram_id, payment.package_key)
        attempt = self._payment_attempts.get(attempt_key)
        if (
            attempt is not None
            and attempt.provider_payment_id == payment.provider_payment_id
        ):
            self._payment_attempts[attempt_key] = LessonPaymentAttempt(
                idempotence_key=attempt.idempotence_key,
                telegram_id=attempt.telegram_id,
                package_key=attempt.package_key,
                package_title=attempt.package_title,
                lessons=attempt.lessons,
                amount_minor=attempt.amount_minor,
                status="completed",
                provider_payment_id=attempt.provider_payment_id,
                confirmation_url=attempt.confirmation_url,
            )
        self._credit_ledger.append(
            (telegram_id, payment.lessons, "purchase", payment.id)
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

    async def cancel_lesson_payment(self, payment_id: int, telegram_id: int) -> bool:
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
            status="canceled",
            package_title=payment.package_title,
        )
        attempt_key = (payment.telegram_id, payment.package_key)
        attempt = self._payment_attempts.get(attempt_key)
        if (
            attempt is not None
            and attempt.provider_payment_id == payment.provider_payment_id
        ):
            self._payment_attempts[attempt_key] = LessonPaymentAttempt(
                idempotence_key=attempt.idempotence_key,
                telegram_id=attempt.telegram_id,
                package_key=attempt.package_key,
                package_title=attempt.package_title,
                lessons=attempt.lessons,
                amount_minor=attempt.amount_minor,
                status="failed",
                provider_payment_id=attempt.provider_payment_id,
                confirmation_url=attempt.confirmation_url,
            )
        return True

    async def prepare_lesson_refund(
        self,
        payment_id: int,
        admin_telegram_id: int,
        reason: str,
    ) -> Optional[LessonRefund]:
        _ = admin_telegram_id
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 300:
            raise ValueError("Причина возврата должна содержать от 1 до 300 символов")
        payment = self._payments.get(payment_id)
        if payment is None:
            return None
        if payment.status == "refund_pending":
            return LessonRefund(
                payment_id=payment.id,
                telegram_id=payment.telegram_id,
                provider_payment_id=payment.provider_payment_id,
                amount_minor=payment.amount_minor,
                lessons=payment.lessons,
                idempotence_key=payment.refund_idempotence_key or uuid.uuid4(),
                provider_refund_id=payment.provider_refund_id,
                reason=payment.refund_reason or normalized_reason,
            )
        if payment.status != "succeeded":
            return None
        profile = self._get_profile(payment.telegram_id)
        payment_credit_balance = self._payment_credit_balance(payment_id)
        if (
            profile.lesson_credits < payment.lessons
            or payment_credit_balance < payment.lessons
        ):
            raise ValueError("Недостаточно неиспользованных занятий для возврата")
        refund_key = uuid.uuid4()
        self._profiles[payment.telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits - payment.lessons,
        )
        self._credit_ledger.append(
            (
                payment.telegram_id,
                -payment.lessons,
                "refund_reservation",
                payment_id,
            )
        )
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="refund_pending",
            refund_idempotence_key=refund_key,
            refund_reason=normalized_reason,
        )
        return LessonRefund(
            payment_id=payment.id,
            telegram_id=payment.telegram_id,
            provider_payment_id=payment.provider_payment_id,
            amount_minor=payment.amount_minor,
            lessons=payment.lessons,
            idempotence_key=refund_key,
            provider_refund_id=None,
            reason=normalized_reason,
        )

    async def record_provider_refund(
        self,
        payment_id: int,
        provider_refund_id: str,
    ) -> None:
        payment = self._payments[payment_id]
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status=payment.status,
            refund_idempotence_key=payment.refund_idempotence_key,
            provider_refund_id=provider_refund_id,
            refund_reason=payment.refund_reason,
        )

    async def complete_lesson_refund(self, payment_id: int) -> bool:
        payment = self._payments.get(payment_id)
        if payment is None or payment.status != "refund_pending":
            return False
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="refunded",
            refund_idempotence_key=payment.refund_idempotence_key,
            provider_refund_id=payment.provider_refund_id,
            refund_reason=payment.refund_reason,
        )
        self._credit_ledger = [
            (
                telegram_id,
                delta,
                "refund"
                if ledger_payment_id == payment_id
                and entry_type == "refund_reservation"
                else entry_type,
                ledger_payment_id,
            )
            for telegram_id, delta, entry_type, ledger_payment_id in self._credit_ledger
        ]
        return True

    async def release_lesson_refund(self, payment_id: int) -> bool:
        payment = self._payments.get(payment_id)
        if payment is None or payment.status != "refund_pending":
            return False
        profile = self._get_profile(payment.telegram_id)
        self._profiles[payment.telegram_id] = UserProfile(
            telegram_id=profile.telegram_id,
            phone=profile.phone,
            user_name=profile.user_name,
            registered_at=profile.registered_at,
            is_admin=profile.is_admin,
            lesson_credits=profile.lesson_credits + payment.lessons,
        )
        self._credit_ledger.append(
            (payment.telegram_id, payment.lessons, "refund_release", payment_id)
        )
        self._payments[payment_id] = LessonPayment(
            id=payment.id,
            telegram_id=payment.telegram_id,
            package_key=payment.package_key,
            package_title=payment.package_title,
            lessons=payment.lessons,
            amount_minor=payment.amount_minor,
            provider_payment_id=payment.provider_payment_id,
            confirmation_url=payment.confirmation_url,
            status="succeeded",
            refund_reason=payment.refund_reason,
        )
        return True

    async def get_lesson_credits(self, telegram_id: int) -> int:
        return self._get_profile(telegram_id).lesson_credits

    async def list_lesson_payments_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 20,
    ) -> Sequence[LessonPaymentHistoryItem]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество платежей должно быть от 1 до 100")
        items = [
            LessonPaymentHistoryItem(
                id=payment.id,
                package_key=payment.package_key,
                package_title=payment.package_title,
                lessons=payment.lessons,
                amount_minor=payment.amount_minor,
                status=payment.status,
                created_at=self._payment_created_at.get(
                    payment.id, datetime.now(timezone.utc)
                ),
            )
            for payment in self._payments.values()
            if payment.telegram_id == telegram_id
        ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:limit]

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

    async def create_class_slot(
        self,
        class_key: str,
        starts_at: datetime,
        capacity: int,
        admin_telegram_id: int,
    ) -> ClassSlot:
        _validate_slot(class_key, starts_at, capacity)
        slot = ClassSlot(
            id=self._next_slot_id,
            class_key=class_key,
            starts_at=starts_at,
            capacity=capacity,
            booked_count=0,
        )
        self._class_slots[slot.id] = slot
        self._next_slot_id += 1
        logger.info(
            "Created in-memory class slot id=%s admin_id=%s",
            slot.id,
            admin_telegram_id,
        )
        return slot

    async def list_class_slots(
        self,
        class_key: Optional[str] = None,
        limit: int = 100,
    ) -> Sequence[ClassSlot]:
        if class_key is not None and class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        slots = [
            self._slot_with_count(slot)
            for slot in self._class_slots.values()
            if slot.starts_at > datetime.now(timezone.utc)
            and (class_key is None or slot.class_key == class_key)
        ]
        return sorted(slots, key=lambda slot: slot.starts_at)[:limit]

    async def list_available_class_slots(
        self,
        class_key: str,
        limit: int = 20,
    ) -> Sequence[ClassSlot]:
        if class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        slots = [
            slot
            for slot in await self.list_class_slots(class_key, limit=100)
            if slot.status == "open" and slot.remaining > 0
        ]
        return slots[:limit]

    async def book_class_slot(
        self,
        slot_id: int,
        telegram_id: int,
    ) -> ClassBooking:
        slot = self._class_slots.get(slot_id)
        if (
            slot is None
            or slot.status != "open"
            or slot.starts_at <= datetime.now(timezone.utc)
        ):
            raise SlotUnavailableError("Слот закрыт или уже недоступен")
        key = (slot_id, telegram_id)
        previous = self._class_bookings.get(key)
        if previous is not None and not previous.already_booked:
            return ClassBooking(
                id=previous.id,
                slot_id=slot_id,
                telegram_id=telegram_id,
                starts_at=slot.starts_at,
                class_key=slot.class_key,
                already_booked=True,
            )
        current_slot = self._slot_with_count(slot)
        if current_slot.booked_count >= current_slot.capacity:
            raise SlotUnavailableError("На это занятие уже нет свободных мест")
        booking = ClassBooking(
            id=self._next_booking_id,
            slot_id=slot_id,
            telegram_id=telegram_id,
            starts_at=slot.starts_at,
            class_key=slot.class_key,
        )
        self._class_bookings[key] = booking
        self._next_booking_id += 1
        self._class_slots[slot_id] = ClassSlot(
            id=slot.id,
            class_key=slot.class_key,
            starts_at=slot.starts_at,
            capacity=slot.capacity,
            booked_count=current_slot.booked_count + 1,
            status=slot.status,
        )
        return booking

    async def list_bookings_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 50,
    ) -> Sequence[UserBooking]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество записей должно быть от 1 до 100")
        bookings = [
            UserBooking(
                id=booking.id,
                slot_id=booking.slot_id,
                class_key=booking.class_key,
                starts_at=booking.starts_at,
                booking_status="confirmed",
                slot_status=self._class_slots[booking.slot_id].status,
            )
            for (slot_id, booking_telegram_id), booking in self._class_bookings.items()
            if booking_telegram_id == telegram_id and not booking.already_booked
        ]
        bookings.sort(key=lambda booking: booking.starts_at, reverse=True)
        return bookings[:limit]

    async def update_class_slot_capacity(self, slot_id: int, capacity: int) -> bool:
        if not 1 <= capacity <= 100:
            raise ValueError("Вместимость слота должна быть от 1 до 100")
        slot = self._class_slots.get(slot_id)
        if slot is None:
            return False
        current = self._slot_with_count(slot)
        if capacity < current.booked_count:
            raise ValueError(
                "Нельзя установить вместимость ниже числа подтверждённых записей"
            )
        self._class_slots[slot_id] = ClassSlot(
            id=slot.id,
            class_key=slot.class_key,
            starts_at=slot.starts_at,
            capacity=capacity,
            booked_count=current.booked_count,
            status=slot.status,
        )
        return True

    async def close_class_slot(self, slot_id: int) -> bool:
        slot = self._class_slots.get(slot_id)
        if slot is None or slot.status != "open":
            return False
        self._class_slots[slot_id] = ClassSlot(
            id=slot.id,
            class_key=slot.class_key,
            starts_at=slot.starts_at,
            capacity=slot.capacity,
            booked_count=slot.booked_count,
            status="closed",
        )
        return True

    def _slot_with_count(self, slot: ClassSlot) -> ClassSlot:
        booked_count = sum(
            1
            for (booking_slot_id, _), booking in self._class_bookings.items()
            if booking_slot_id == slot.id and not booking.already_booked
        )
        return ClassSlot(
            id=slot.id,
            class_key=slot.class_key,
            starts_at=slot.starts_at,
            capacity=slot.capacity,
            booked_count=booked_count,
            status=slot.status,
        )

    async def list_admin_ids(self) -> Sequence[int]:
        return sorted(
            profile.telegram_id
            for profile in self._profiles.values()
            if profile.is_admin
        )

    async def create_support_message(
        self,
        telegram_id: int,
        body: str,
    ) -> tuple[int, bool]:
        normalized = _validate_support_body(body)
        now = datetime.now(timezone.utc)
        ticket = next(
            (
                item
                for item in self._support_tickets.values()
                if item.telegram_id == telegram_id and item.status == "open"
            ),
            None,
        )
        created = ticket is None
        if ticket is None:
            ticket = SupportTicket(
                id=self._next_support_ticket_id,
                telegram_id=telegram_id,
                status="open",
                created_at=now,
                updated_at=now,
            )
            self._support_tickets[ticket.id] = ticket
            self._support_messages[ticket.id] = []
            self._next_support_ticket_id += 1
        self._support_messages[ticket.id].append(
            SupportMessage(ticket.id, telegram_id, "user", normalized)
        )
        self._support_tickets[ticket.id] = SupportTicket(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=now,
        )
        return ticket.id, created

    async def reply_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
        body: str,
    ) -> Optional[int]:
        normalized = _validate_support_body(body)
        ticket = self._support_tickets.get(ticket_id)
        if ticket is None or ticket.status != "open":
            return None
        self._support_messages[ticket_id].append(
            SupportMessage(ticket_id, admin_telegram_id, "admin", normalized)
        )
        self._support_tickets[ticket_id] = SupportTicket(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status=ticket.status,
            created_at=ticket.created_at,
            updated_at=datetime.now(timezone.utc),
            last_message=normalized,
        )
        return ticket.telegram_id

    async def list_open_support_tickets(
        self,
        limit: int = 20,
    ) -> Sequence[SupportTicket]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество обращений должно быть от 1 до 100")
        tickets = [
            SupportTicket(
                id=ticket.id,
                telegram_id=ticket.telegram_id,
                status=ticket.status,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                last_message=(
                    self._support_messages[ticket.id][-1].body
                    if self._support_messages[ticket.id]
                    else ""
                ),
            )
            for ticket in self._support_tickets.values()
            if ticket.status == "open"
        ]
        tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
        return tickets[:limit]

    async def list_support_tickets_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 20,
    ) -> Sequence[SupportTicket]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество обращений должно быть от 1 до 100")
        tickets = [
            SupportTicket(
                id=ticket.id,
                telegram_id=ticket.telegram_id,
                status=ticket.status,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                last_message=(
                    self._support_messages[ticket.id][-1].body
                    if self._support_messages[ticket.id]
                    else ""
                ),
            )
            for ticket in self._support_tickets.values()
            if ticket.telegram_id == telegram_id
        ]
        tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
        return tickets[:limit]

    async def close_support_ticket(
        self,
        ticket_id: int,
        admin_telegram_id: int,
    ) -> Optional[int]:
        _ = admin_telegram_id
        ticket = self._support_tickets.get(ticket_id)
        if ticket is None or ticket.status != "open":
            return None
        self._support_tickets[ticket_id] = SupportTicket(
            id=ticket.id,
            telegram_id=ticket.telegram_id,
            status="closed",
            created_at=ticket.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        return ticket.telegram_id

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
        if request.kind == "booking":
            profile = self._get_profile(request.telegram_id)
            if profile.lesson_credits > 0:
                self._profiles[request.telegram_id] = UserProfile(
                    telegram_id=profile.telegram_id,
                    phone=profile.phone,
                    user_name=profile.user_name,
                    registered_at=profile.registered_at,
                    is_admin=profile.is_admin,
                    lesson_credits=profile.lesson_credits - 1,
                )
                legacy_credits = profile.lesson_credits - sum(
                    max(0, self._payment_credit_balance(payment.id))
                    for payment in self._payments.values()
                    if payment.telegram_id == request.telegram_id
                    and payment.status == "succeeded"
                )
                source_payment_id = None
                if legacy_credits <= 0:
                    for payment in self._payments.values():
                        if (
                            payment.telegram_id == request.telegram_id
                            and payment.status == "succeeded"
                            and self._payment_credit_balance(payment.id) > 0
                        ):
                            source_payment_id = payment.id
                            break
                self._credit_ledger.append(
                    (
                        request.telegram_id,
                        -1,
                        "lesson_use",
                        source_payment_id,
                    )
                )
        return True

    def _get_profile(self, telegram_id: int) -> UserProfile:
        profile = self._profiles.get(telegram_id)
        if profile is None:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            )
        return profile

    def _payment_credit_balance(self, payment_id: int) -> int:
        return sum(
            delta
            for _, delta, _, ledger_payment_id in self._credit_ledger
            if ledger_payment_id == payment_id
        )

    async def create_web_user(
        self,
        email: str,
        password_hash: str,
        display_name: str,
    ) -> WebUserRecord:
        normalized_email = email.lower()
        if any(
            user.email is not None and user.email.lower() == normalized_email
            for user in self._web_users.values()
        ):
            raise EmailAlreadyRegisteredError("Этот email уже зарегистрирован")
        user = WebUserRecord(
            id=self._next_web_user_id,
            email=email,
            password_hash=password_hash,
            telegram_id=None,
            display_name=display_name,
            created_at=datetime.now(timezone.utc),
        )
        self._web_users[user.id] = user
        self._next_web_user_id += 1
        return user

    async def get_or_create_web_user_from_telegram(
        self,
        telegram_id: int,
        display_name: str,
    ) -> WebUserRecord:
        existing = await self.get_web_user_by_telegram_id(telegram_id)
        if existing is not None:
            return existing
        user = WebUserRecord(
            id=self._next_web_user_id,
            email=None,
            password_hash=None,
            telegram_id=telegram_id,
            display_name=display_name,
            created_at=datetime.now(timezone.utc),
        )
        self._web_users[user.id] = user
        self._next_web_user_id += 1
        return user

    async def get_web_user_by_id(self, user_id: int) -> Optional[WebUserRecord]:
        return self._web_users.get(user_id)

    async def get_web_user_by_email(self, email: str) -> Optional[WebUserRecord]:
        normalized_email = email.lower()
        for user in self._web_users.values():
            if user.email is not None and user.email.lower() == normalized_email:
                return user
        return None

    async def get_web_user_by_telegram_id(
        self,
        telegram_id: int,
    ) -> Optional[WebUserRecord]:
        for user in self._web_users.values():
            if user.telegram_id == telegram_id:
                return user
        return None

    async def set_web_user_telegram_id(
        self,
        user_id: int,
        telegram_id: Optional[int],
    ) -> bool:
        user = self._web_users.get(user_id)
        if user is None:
            return False
        if telegram_id is not None and any(
            other.id != user_id and other.telegram_id == telegram_id
            for other in self._web_users.values()
        ):
            raise TelegramAlreadyLinkedError(
                "Этот Telegram уже привязан к другому аккаунту"
            )
        self._web_users[user_id] = WebUserRecord(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            telegram_id=telegram_id,
            display_name=user.display_name,
            created_at=user.created_at,
        )
        return True
