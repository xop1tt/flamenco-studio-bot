import errno
import hashlib
import logging
import ipaddress
import socket
import ssl
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

import asyncpg

from .studio_models import CreditSource


logger = logging.getLogger("bot.database")
MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"
MIGRATION_LOCK_ID = 715_203_401
CLASS_KEYS = {"beginner", "intermediate", "individual"}
MAX_SUPPORT_MESSAGE_LENGTH = 2000
# Бизнес-правила бронирования слотов, подтверждённые владельцем продукта
# (не придуманы в коде, см. обсуждение аудита):
# - запись стоит 1 lesson_credit, отмена возвращает его;
# - отменить можно не позднее чем за 24 часа до начала занятия;
# - после отмены тот же пользователь не может повторно записаться на тот же
#   слот в течение 12 часов (чтобы не злоупотреблять отменой/записью).
BOOKING_CANCELLATION_DEADLINE = timedelta(hours=24)
BOOKING_REBOOK_COOLDOWN = timedelta(hours=12)


def booking_cancellation_deadline(
    starts_at: datetime,
    booked_at: Optional[datetime] = None,
    rescheduled_at: Optional[datetime] = None,
) -> datetime:
    """До какого момента участник может отменить запись.

    Обычно — не позднее чем за 24 часа до начала. Если студия перенесла
    занятие после того, как участник записался, новое время участник не
    выбирал: такую запись можно отменить до нового начала (правило
    продуктового roadmap, этап 2 «Перенос»).
    """
    if (
        rescheduled_at is not None
        and booked_at is not None
        and booked_at <= rescheduled_at
    ):
        return starts_at
    return starts_at - BOOKING_CANCELLATION_DEADLINE


def check_cancellation_window(
    starts_at: datetime,
    booked_at: Optional[datetime],
    rescheduled_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> None:
    """``CancellationWindowExpiredError``, если отменять запись уже поздно."""
    current = now or datetime.now(timezone.utc)
    deadline = booking_cancellation_deadline(starts_at, booked_at, rescheduled_at)
    if deadline == starts_at:
        if current >= starts_at:
            raise CancellationWindowExpiredError(
                "Занятие уже началось — отменить запись нельзя"
            )
    elif current > deadline:
        raise CancellationWindowExpiredError(
            "Отмена доступна не позднее чем за 24 часа до начала занятия"
        )


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
    # Отмена студией (status = 'cancelled') и последний перенос.
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    rescheduled_at: Optional[datetime] = None

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
            cancelled_at=record.get("cancelled_at"),
            cancel_reason=record.get("cancel_reason"),
            rescheduled_at=record.get("rescheduled_at"),
        )


@dataclass(frozen=True)
class ClassBooking:
    id: int
    slot_id: int
    telegram_id: int
    starts_at: datetime
    class_key: str
    already_booked: bool = False
    # Баланс после списания и абонемент, с которого списано занятие
    # (None — с занятий вне абонементов). Заполняются только для новой записи.
    balance: Optional[int] = None
    source: Optional[CreditSource] = None


@dataclass(frozen=True)
class UserBooking:
    """Запись участника на занятие вместе со статусом брони и слота.

    В отличие от ``ClassBooking`` (результат одного вызова ``book_class_slot``)
    используется для списков "мои занятия": несёт и статус брони
    (confirmed/cancelled), и статус самого слота (open/closed/cancelled).
    """

    id: int
    slot_id: int
    class_key: str
    starts_at: datetime
    booking_status: str
    slot_status: str
    booked_at: Optional[datetime] = None
    # 'user' — отменил участник, 'studio' — занятие отменила студия.
    cancelled_by: Optional[str] = None
    rescheduled_at: Optional[datetime] = None
    # Время занятия до последнего переноса студией.
    previous_starts_at: Optional[datetime] = None
    slot_cancel_reason: Optional[str] = None

    @property
    def cancellation_deadline(self) -> datetime:
        return booking_cancellation_deadline(
            self.starts_at, self.booked_at, self.rescheduled_at
        )

    def can_cancel(self, now: Optional[datetime] = None) -> bool:
        """Подсказка интерфейсу; окончательно решает репозиторий."""
        current = now or datetime.now(timezone.utc)
        return (
            self.booking_status == "confirmed"
            and self.slot_status != "cancelled"
            and current < self.starts_at
            and current <= self.cancellation_deadline
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "UserBooking":
        return cls(
            id=record["id"],
            slot_id=record["slot_id"],
            class_key=record["class_key"],
            starts_at=record["starts_at"],
            booking_status=record["booking_status"],
            slot_status=record["slot_status"],
            booked_at=record.get("booked_at"),
            cancelled_by=record.get("cancelled_by"),
            rescheduled_at=record.get("rescheduled_at"),
            previous_starts_at=record.get("previous_starts_at"),
            slot_cancel_reason=record.get("slot_cancel_reason"),
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
    created_at: Optional[datetime] = None


class SlotUnavailableError(RuntimeError):
    """Raised when a class slot is closed, full, or no longer in the future."""


class InsufficientLessonCreditsError(RuntimeError):
    """Raised when the user has no lesson credits left to spend on a booking."""


class BookingCooldownError(RuntimeError):
    """Raised when rebooking a slot the same user just cancelled too recently."""


class BookingNotFoundError(RuntimeError):
    """Raised when cancelling a booking that does not exist for this user."""


class CancellationWindowExpiredError(RuntimeError):
    """Raised when cancelling a booking too close to the class start time."""


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
class PendingLessonPayment:
    """Платёж без решения ЮKassa, видный фоновой сверке (а не только истории).

    ЮKassa не шлёт вебхук — платёж подтверждается только тогда, когда кто-то
    вызывает ``PaymentService.check_payment`` (пользователь/админ нажал
    "проверить статус"). Эта запись — минимум, нужный фоновой задаче, чтобы
    сделать то же самое за пользователя, который не вернулся сам.
    """

    id: int
    telegram_id: int
    created_at: datetime

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "PendingLessonPayment":
        return cls(
            id=record["id"],
            telegram_id=record["telegram_id"],
            created_at=record["created_at"],
        )


@dataclass(frozen=True)
class CreditAdjustment:
    """Результат ручной корректировки баланса занятий администратором."""

    ledger_id: int
    telegram_id: int
    delta: int
    balance: int
    # False — операция с этим ключом идемпотентности уже была выполнена
    # раньше; баланс при повторе не менялся.
    applied: bool


@dataclass(frozen=True)
class CreditBalanceMismatch:
    """Пользователь, у которого bot_users.lesson_credits != SUM(ledger.delta)."""

    telegram_id: int
    user_name: str
    lesson_credits: int
    ledger_total: int
    ledger_entries: int
    last_entry_at: Optional[datetime]

    @property
    def difference(self) -> int:
        """Насколько баланс больше суммы ledger (отрицательное — меньше)."""
        return self.lesson_credits - self.ledger_total


@dataclass(frozen=True)
class CreditReconciliation:
    checked_users: int
    # Всего расхождений; ``mismatches`` может содержать только первые limit.
    mismatched_users: int
    mismatches: Sequence[CreditBalanceMismatch]


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


# Имя участника — одно: bot_users.user_name (его меняют и бот, и сайт через
# PATCH /api/users/me/profile). users.display_name — лишь имя на момент
# создания веб-аккаунта; используется, только пока Telegram не привязан.
_WEB_USER_SELECT = """
    SELECT account.id, account.email, account.password_hash, account.telegram_id,
           COALESCE(profile.user_name, account.display_name) AS display_name,
           account.created_at
    FROM users AS account
    LEFT JOIN bot_users AS profile ON profile.telegram_id = account.telegram_id
"""


class EmailAlreadyRegisteredError(ValueError):
    """На этот email уже зарегистрирован веб-аккаунт."""


class TelegramAlreadyLinkedError(ValueError):
    """Этот Telegram уже привязан к другому веб-аккаунту."""


# Методы жизненного цикла занятий, абонементов, истории, уведомлений и входа
# через бота вынесены в отдельные модули только из-за размера файла. Импорт
# стоит здесь, а не в начале: модулю нужны типы, объявленные выше.
from .studio_postgres import PostgresStudioMixin  # noqa: E402


class PostgresRepository(PostgresStudioMixin):
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

    @asynccontextmanager
    async def try_advisory_lock(self, lock_id: int) -> AsyncIterator[bool]:
        """Неблокирующая сессионная advisory-блокировка на время блока.

        Отдаёт ``False``, если её уже держит другой процесс (бот или API) —
        так фоновую задачу выполняет только один экземпляр. Блокировка
        привязана к соединению: при падении процесса PostgreSQL снимает её
        сама.
        """
        async with self._pool.acquire() as connection:
            acquired = await connection.fetchval(
                "SELECT pg_try_advisory_lock($1)", lock_id
            )
            try:
                yield bool(acquired)
            finally:
                if acquired:
                    try:
                        await connection.execute(
                            "SELECT pg_advisory_unlock($1)", lock_id
                        )
                    except Exception:
                        # Соединение с неснятой блокировкой нельзя вернуть
                        # в пул — закрываем, и PostgreSQL снимет её сам.
                        logger.exception("Failed to release advisory lock")
                        connection.terminate()

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
                await self._change_credits(
                    connection,
                    telegram_id,
                    record["lessons"],
                    "purchase",
                    "payment:{}".format(payment_id),
                    payment_id=payment_id,
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
                    WHERE telegram_id = $1 FOR NO KEY UPDATE
                    """,
                    payment["telegram_id"],
                )
                # 'adjustment' и 'slot_cancellation' с payment_id — возврат
                # занятия этого абонемента при отмене записи участником или
                # студией: без них отменённая запись выглядела бы
                # использованным занятием и блокировала возврат оплаты.
                payment_credit_balance = await connection.fetchval(
                    """
                    SELECT COALESCE(SUM(delta), 0)
                    FROM lesson_credit_ledger
                    WHERE payment_id = $1
                      AND entry_type IN (
                          'purchase', 'lesson_use', 'refund_reservation',
                          'refund', 'refund_release', 'adjustment',
                          'slot_cancellation'
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
                await self._change_credits(
                    connection,
                    payment["telegram_id"],
                    -payment["lessons"],
                    "refund_reservation",
                    "refund-reservation:{}:{}".format(payment_id, refund_key),
                    payment_id=payment_id,
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
                await self._change_credits(
                    connection,
                    payment["telegram_id"],
                    payment["lessons"],
                    "refund_release",
                    "refund-release:{}:{}".format(payment_id, uuid.uuid4()),
                    payment_id=payment_id,
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

    @staticmethod
    async def _change_credits(
        connection: Any,
        telegram_id: int,
        delta: int,
        entry_type: str,
        reference_key: str,
        *,
        payment_id: Optional[int] = None,
        grant_id: Optional[int] = None,
        booking_id: Optional[int] = None,
        actor_telegram_id: Optional[int] = None,
        reason: Optional[str] = None,
        insufficient_message: str = "На балансе недостаточно занятий",
    ) -> Optional[Tuple[int, int]]:
        """Единственное место, где меняется ``bot_users.lesson_credits``.

        Пишет строку ledger и меняет баланс в одной транзакции вызывающего
        (``connection`` обязан быть внутри ``connection.transaction()``):
        баланс и ledger не могут разойтись, а баланс не может стать
        отрицательным (``InsufficientLessonCreditsError``; тот же запрет
        дублирует CHECK в БД). ``reference_key`` уникален: если операция с
        таким ключом уже записана, возвращается ``None`` и баланс не
        трогается — так повтор детерминированной операции (например,
        ``payment:<id>``) идемпотентен. Иначе возвращает
        ``(id строки ledger, новый баланс)``.

        ``payment_id`` / ``grant_id`` — абонемент, к которому относится
        движение (остаток абонемента — сумма ledger по нему); ``booking_id``
        — запись на занятие, за которую списано или возвращено занятие.
        """
        if delta == 0:
            raise ValueError("Изменение баланса не может быть нулевым")
        if not connection.is_in_transaction():
            raise RuntimeError("Баланс занятий меняется только внутри транзакции")
        try:
            ledger_id = await connection.fetchval(
                """
                INSERT INTO lesson_credit_ledger (
                    telegram_id, payment_id, entry_type, delta, reference_key,
                    actor_telegram_id, reason, grant_id, booking_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (reference_key) DO NOTHING
                RETURNING id
                """,
                telegram_id,
                payment_id,
                entry_type,
                delta,
                reference_key,
                actor_telegram_id,
                reason,
                grant_id,
                booking_id,
            )
        except asyncpg.ForeignKeyViolationError as error:
            raise LookupError(
                "Профиль не найден для Telegram ID {}".format(telegram_id)
            ) from error
        if ledger_id is None:
            return None
        balance = await connection.fetchval(
            """
            UPDATE bot_users
            SET lesson_credits = lesson_credits + $2
            WHERE telegram_id = $1 AND lesson_credits + $2 >= 0
            RETURNING lesson_credits
            """,
            telegram_id,
            delta,
        )
        if balance is None:
            # Профиль точно есть (внешний ключ ledger выше его проверил):
            # значит, не хватило занятий. Исключение откатывает и строку ledger.
            raise InsufficientLessonCreditsError(insufficient_message)
        return ledger_id, balance

    async def adjust_lesson_credits(
        self,
        telegram_id: int,
        delta: int,
        reason: str,
        actor_telegram_id: int,
        idempotence_key: uuid.UUID,
    ) -> CreditAdjustment:
        """Ручная корректировка баланса администратором.

        ``PermissionError`` — ``actor_telegram_id`` не администратор;
        ``LookupError`` — нет профиля; ``InsufficientLessonCreditsError`` —
        списание увело бы баланс ниже нуля; ``ValueError`` — пустая или
        слишком длинная причина, нулевой delta либо ключ идемпотентности уже
        использован для другой операции. Повтор с тем же ключом баланс не
        меняет и возвращает прежний результат с ``applied=False``.
        """
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 300:
            raise ValueError("Причина должна содержать от 1 до 300 символов")
        if delta == 0:
            raise ValueError("Изменение баланса не может быть нулевым")
        reference_key = "admin-adjustment:{}".format(idempotence_key)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                is_admin = await connection.fetchval(
                    "SELECT is_admin FROM bot_users WHERE telegram_id = $1",
                    actor_telegram_id,
                )
                if not is_admin:
                    raise PermissionError("Корректировку может выполнить только админ")
                changed = await self._change_credits(
                    connection,
                    telegram_id,
                    delta,
                    "admin_adjustment",
                    reference_key,
                    actor_telegram_id=actor_telegram_id,
                    reason=normalized_reason,
                    insufficient_message=(
                        "Баланс не может стать отрицательным: у участника "
                        "недостаточно занятий"
                    ),
                )
                if changed is not None:
                    ledger_id, balance = changed
                    applied = True
                else:
                    previous = await connection.fetchrow(
                        """
                        SELECT id, telegram_id, delta FROM lesson_credit_ledger
                        WHERE reference_key = $1
                        """,
                        reference_key,
                    )
                    if (
                        previous["telegram_id"] != telegram_id
                        or previous["delta"] != delta
                    ):
                        raise ValueError(
                            "Ключ идемпотентности уже использован для другой "
                            "корректировки"
                        )
                    ledger_id = previous["id"]
                    balance = await connection.fetchval(
                        "SELECT lesson_credits FROM bot_users WHERE telegram_id = $1",
                        telegram_id,
                    )
                    applied = False
        if applied:
            logger.warning(
                "Lesson credits adjusted telegram_id=%s delta=%s actor_id=%s "
                "ledger_id=%s",
                telegram_id,
                delta,
                actor_telegram_id,
                ledger_id,
            )
        return CreditAdjustment(
            ledger_id=ledger_id,
            telegram_id=telegram_id,
            delta=delta,
            balance=balance,
            applied=applied,
        )

    async def get_credit_reconciliation(self, limit: int = 50) -> CreditReconciliation:
        """Сверка ``bot_users.lesson_credits`` с суммой ledger. Только чтение."""
        if not 1 <= limit <= 500:
            raise ValueError("Лимит списка должен быть от 1 до 500")
        async with self._pool.acquire() as connection:
            # Один снимок для обоих запросов: параллельная запись или оплата
            # не должна выглядеть расхождением.
            async with connection.transaction(
                isolation="repeatable_read", readonly=True
            ):
                checked_users = await connection.fetchval(
                    "SELECT COUNT(*) FROM bot_users"
                )
                records = await connection.fetch(
                    """
                    SELECT telegram_id, user_name, lesson_credits, ledger_total,
                           ledger_entries, last_entry_at,
                           COUNT(*) OVER () AS mismatched_users
                    FROM (
                        SELECT profile.telegram_id, profile.user_name,
                               profile.lesson_credits,
                               COALESCE(SUM(ledger.delta), 0)::BIGINT AS ledger_total,
                               COUNT(ledger.id) AS ledger_entries,
                               MAX(ledger.created_at) AS last_entry_at
                        FROM bot_users AS profile
                        LEFT JOIN lesson_credit_ledger AS ledger
                          ON ledger.telegram_id = profile.telegram_id
                        GROUP BY profile.telegram_id
                    ) AS totals
                    WHERE lesson_credits <> ledger_total
                    ORDER BY ABS(lesson_credits - ledger_total) DESC, telegram_id
                    LIMIT $1
                    """,
                    limit,
                )
        return CreditReconciliation(
            checked_users=checked_users,
            mismatched_users=records[0]["mismatched_users"] if records else 0,
            mismatches=[
                CreditBalanceMismatch(
                    telegram_id=record["telegram_id"],
                    user_name=record["user_name"],
                    lesson_credits=record["lesson_credits"],
                    ledger_total=record["ledger_total"],
                    ledger_entries=record["ledger_entries"],
                    last_entry_at=record["last_entry_at"],
                )
                for record in records
            ],
        )

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

    async def list_pending_lesson_payments_older_than(
        self,
        cutoff: datetime,
        limit: int = 200,
    ) -> Sequence[PendingLessonPayment]:
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT id, telegram_id, created_at
                FROM lesson_payments
                WHERE status = 'pending' AND created_at < $1
                ORDER BY created_at
                LIMIT $2
                """,
                cutoff,
                limit,
            )
        return [PendingLessonPayment.from_record(record) for record in records]

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
                _WEB_USER_SELECT + "WHERE account.id = $1",
                user_id,
            )
        return WebUserRecord.from_record(record) if record is not None else None

    async def create_web_session(
        self,
        user_id: int,
        token: str,
        expires_at: datetime,
    ) -> None:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                # Чистим собственные просроченные сессии пользователя —
                # простая защита от бесконечного роста таблицы без отдельной
                # фоновой задачи.
                await connection.execute(
                    """
                    DELETE FROM web_sessions
                    WHERE user_id = $1 AND expires_at <= NOW()
                    """,
                    user_id,
                )
                await connection.execute(
                    """
                    INSERT INTO web_sessions (token_hash, user_id, expires_at)
                    VALUES ($1, $2, $3)
                    """,
                    hash_session_token(token),
                    user_id,
                    expires_at,
                )

    async def get_web_session_user_id(self, token: str) -> Optional[int]:
        async with self._pool.acquire() as connection:
            return await connection.fetchval(
                """
                SELECT user_id FROM web_sessions
                WHERE token_hash = $1 AND expires_at > NOW()
                """,
                hash_session_token(token),
            )

    async def delete_web_session(self, token: str) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM web_sessions WHERE token_hash = $1",
                hash_session_token(token),
            )

    async def get_web_user_by_email(self, email: str) -> Optional[WebUserRecord]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                _WEB_USER_SELECT + "WHERE LOWER(account.email) = LOWER($1)",
                email,
            )
        return WebUserRecord.from_record(record) if record is not None else None

    async def get_web_user_by_telegram_id(
        self,
        telegram_id: int,
    ) -> Optional[WebUserRecord]:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                _WEB_USER_SELECT + "WHERE account.telegram_id = $1",
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
            async with connection.transaction():
                record = await connection.fetchrow(
                    """
                    INSERT INTO lesson_slots (
                        class_key, starts_at, capacity, created_by
                    )
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, class_key, starts_at, capacity,
                              0 AS booked_count, status
                    """,
                    class_key,
                    starts_at,
                    capacity,
                    admin_telegram_id,
                )
                await connection.execute(
                    """
                    INSERT INTO lesson_slot_events (
                        slot_id, event_type, actor_telegram_id, new_starts_at,
                        new_capacity
                    )
                    VALUES ($1, 'created', $2, $3, $4)
                    """,
                    record["id"],
                    admin_telegram_id,
                    starts_at,
                    capacity,
                )
        logger.info("Created class slot id=%s class=%s", record["id"], class_key)
        return ClassSlot.from_record(record)

    async def list_class_slots(
        self,
        class_key: Optional[str] = None,
        limit: int = 100,
        include_cancelled: bool = False,
        starts_after: Optional[datetime] = None,
    ) -> Sequence[ClassSlot]:
        """Слоты, начинающиеся после ``starts_after`` (по умолчанию — сейчас).

        Отменённые студией слоты по умолчанию не показываются: публичному
        расписанию и списку записи они не нужны; админ-расписание передаёт
        ``include_cancelled=True``.
        """
        if class_key is not None and class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT slot.id, slot.class_key, slot.starts_at, slot.capacity,
                       slot.status, slot.cancelled_at, slot.cancel_reason,
                       slot.rescheduled_at,
                       COUNT(booking.id) FILTER (
                           WHERE booking.status = 'confirmed'
                       )::INTEGER AS booked_count
                FROM lesson_slots AS slot
                LEFT JOIN lesson_bookings AS booking ON booking.slot_id = slot.id
                WHERE slot.starts_at > COALESCE($3::TIMESTAMPTZ, NOW())
                  AND ($1::TEXT IS NULL OR slot.class_key = $1)
                  AND ($4::BOOLEAN OR slot.status <> 'cancelled')
                GROUP BY slot.id
                ORDER BY slot.starts_at
                LIMIT $2
                """,
                class_key,
                limit,
                starts_after,
                include_cancelled,
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
        notify_user: bool = False,
    ) -> ClassBooking:
        """Подтверждает место и списывает 1 занятие в одной транзакции.

        Занятие списывается с абонемента по правилу ``pick_credit_source_index``
        (сначала занятия вне абонементов, затем самый ранний абонемент) —
        в ledger сохраняются и абонемент, и бронь. ``notify_user`` ставит
        уведомление о записи в outbox (сайт; бот показывает результат сам).
        """
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
                    SELECT id, status, updated_at FROM lesson_bookings
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
                if existing is not None and existing["status"] == "cancelled":
                    cooldown_ends_at = existing["updated_at"] + BOOKING_REBOOK_COOLDOWN
                    now = datetime.now(timezone.utc)
                    if now < cooldown_ends_at:
                        hours_left = ceil(
                            (cooldown_ends_at - now).total_seconds() / 3600
                        )
                        raise BookingCooldownError(
                            "Повторная запись на это занятие после отмены "
                            "будет доступна через {} ч.".format(hours_left)
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
                          AND lesson_bookings.updated_at <= NOW() - $3::INTERVAL
                    RETURNING id
                    """,
                    slot_id,
                    telegram_id,
                    # Та же константа, что в проверке выше — правило в одном месте.
                    BOOKING_REBOOK_COOLDOWN,
                )
                if booking is None:
                    raise SlotUnavailableError("Не удалось подтвердить место")

                # Списание после вставки брони: ключу ledger нужен её id. При
                # нехватке занятий исключение откатывает всю транзакцию,
                # включая только что созданную бронь.
                source, low_balance_enabled = await self._pick_credit_source(
                    connection, telegram_id
                )
                _, balance = await self._change_credits(
                    connection,
                    telegram_id,
                    -1,
                    "lesson_use",
                    "slot_booking:{}:use:{}".format(booking["id"], uuid.uuid4()),
                    payment_id=(
                        source.id
                        if source is not None and source.kind == "payment"
                        else None
                    ),
                    grant_id=(
                        source.id
                        if source is not None and source.kind == "grant"
                        else None
                    ),
                    booking_id=booking["id"],
                    insufficient_message=(
                        "На балансе нет доступных занятий. Купите абонемент, "
                        "чтобы записаться."
                    ),
                )
                if source is not None:
                    source = replace(source, remaining=max(0, source.remaining - 1))
                if notify_user:
                    await self._enqueue_notification(
                        connection,
                        telegram_id,
                        "booking_confirmed",
                        {
                            "slot_id": slot_id,
                            "class_key": slot["class_key"],
                            "starts_at": slot["starts_at"].isoformat(),
                            "balance": balance,
                            "source_title": source.title if source else None,
                        },
                        "booking_confirmed:{}:{}".format(booking["id"], uuid.uuid4()),
                    )
                if low_balance_enabled:
                    await self._enqueue_low_balance(connection, telegram_id, balance)
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
            balance=balance,
            source=source,
        )

    async def cancel_class_slot_booking(
        self,
        slot_id: int,
        telegram_id: int,
        notify_user: bool = False,
    ) -> bool:
        """Отменяет подтверждённую запись и возвращает потраченный кредит.

        Идемпотентна: повторный вызов для уже отменённой записи возвращает
        ``False`` без повторного начисления кредита. Занятие возвращается в
        тот же абонемент, с которого было списано.
        """
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                slot = await connection.fetchrow(
                    """
                    SELECT starts_at, class_key, status, rescheduled_at
                    FROM lesson_slots WHERE id = $1 FOR UPDATE
                    """,
                    slot_id,
                )
                if slot is None:
                    raise BookingNotFoundError("Запись не найдена")

                booking = await connection.fetchrow(
                    """
                    SELECT id, status, booked_at FROM lesson_bookings
                    WHERE slot_id = $1 AND telegram_id = $2
                    FOR UPDATE
                    """,
                    slot_id,
                    telegram_id,
                )
                if booking is None:
                    raise BookingNotFoundError("Запись не найдена")
                if booking["status"] != "confirmed":
                    return False

                check_cancellation_window(
                    slot["starts_at"],
                    booking["booked_at"],
                    slot["rescheduled_at"],
                )

                await connection.execute(
                    """
                    UPDATE lesson_bookings
                    SET status = 'cancelled', updated_at = NOW()
                    WHERE id = $1
                    """,
                    booking["id"],
                )
                source = await connection.fetchrow(
                    """
                    SELECT payment_id, grant_id FROM lesson_credit_ledger
                    WHERE booking_id = $1 AND entry_type = 'lesson_use'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    booking["id"],
                )
                _, balance = await self._change_credits(
                    connection,
                    telegram_id,
                    1,
                    "adjustment",
                    "slot_booking:{}:refund:{}".format(booking["id"], uuid.uuid4()),
                    payment_id=source["payment_id"] if source else None,
                    grant_id=source["grant_id"] if source else None,
                    booking_id=booking["id"],
                )
                if notify_user:
                    await self._enqueue_notification(
                        connection,
                        telegram_id,
                        "booking_cancelled",
                        {
                            "slot_id": slot_id,
                            "class_key": slot["class_key"],
                            "starts_at": slot["starts_at"].isoformat(),
                            "balance": balance,
                        },
                        "booking_cancelled:{}:{}".format(booking["id"], uuid.uuid4()),
                    )
        logger.info(
            "Cancelled class booking slot_id=%s telegram_id=%s",
            slot_id,
            telegram_id,
        )
        return True

    async def list_bookings_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[UserBooking]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество записей должно быть от 1 до 100")
        if offset < 0:
            raise ValueError("Смещение списка не может быть отрицательным")
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT booking.id, booking.slot_id, slot.class_key,
                       slot.starts_at, booking.status AS booking_status,
                       slot.status AS slot_status, booking.booked_at,
                       slot.rescheduled_at, slot.cancel_reason AS slot_cancel_reason,
                       CASE
                           WHEN booking.status <> 'cancelled' THEN NULL
                           WHEN slot.status = 'cancelled'
                                AND booking.updated_at >= slot.cancelled_at
                           THEN 'studio'
                           ELSE 'user'
                       END AS cancelled_by,
                       moved.old_starts_at AS previous_starts_at
                FROM lesson_bookings AS booking
                JOIN lesson_slots AS slot ON slot.id = booking.slot_id
                LEFT JOIN LATERAL (
                    SELECT event.old_starts_at
                    FROM lesson_slot_events AS event
                    WHERE event.slot_id = slot.id
                      AND event.event_type = 'rescheduled'
                    ORDER BY event.id DESC
                    LIMIT 1
                ) AS moved ON TRUE
                WHERE booking.telegram_id = $1
                ORDER BY slot.starts_at DESC, booking.id DESC
                LIMIT $2 OFFSET $3
                """,
                telegram_id,
                limit,
                offset,
            )
        return [UserBooking.from_record(record) for record in records]

    async def update_class_slot_capacity(
        self,
        slot_id: int,
        capacity: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        if not 1 <= capacity <= 100:
            raise ValueError("Вместимость слота должна быть от 1 до 100")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                slot = await connection.fetchrow(
                    """
                    SELECT id, capacity, status FROM lesson_slots
                    WHERE id = $1 FOR UPDATE
                    """,
                    slot_id,
                )
                if slot is None:
                    return False
                if slot["status"] == "cancelled":
                    raise ValueError("Занятие отменено — вместимость не меняется")
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
                if capacity != slot["capacity"]:
                    await connection.execute(
                        """
                        INSERT INTO lesson_slot_events (
                            slot_id, event_type, actor_telegram_id,
                            old_capacity, new_capacity
                        )
                        VALUES ($1, 'capacity_changed', $2, $3, $4)
                        """,
                        slot_id,
                        admin_telegram_id,
                        slot["capacity"],
                        capacity,
                    )
        return True

    async def close_class_slot(
        self,
        slot_id: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                closed = await connection.fetchval(
                    """
                    UPDATE lesson_slots SET status = 'closed', updated_at = NOW()
                    WHERE id = $1 AND status = 'open'
                    RETURNING id
                    """,
                    slot_id,
                )
                if closed is not None:
                    await connection.execute(
                        """
                        INSERT INTO lesson_slot_events (
                            slot_id, event_type, actor_telegram_id
                        )
                        VALUES ($1, 'closed', $2)
                        """,
                        slot_id,
                        admin_telegram_id,
                    )
        return closed is not None

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
                    current_credits = await connection.fetchval(
                        """
                        SELECT lesson_credits FROM bot_users
                        WHERE telegram_id = $1
                        FOR NO KEY UPDATE
                        """,
                        request["telegram_id"],
                    )
                    # Без занятий на балансе заявка просто закрывается.
                    if current_credits:
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
                        debit = await self._change_credits(
                            connection,
                            request["telegram_id"],
                            -1,
                            "lesson_use",
                            "request:{}".format(request_id),
                            payment_id=(
                                payment_credit["id"]
                                if payment_credit is not None
                                else None
                            ),
                        )
                        if debit is not None:
                            logger.info(
                                "Debited lesson credit request_id=%s "
                                "telegram_id=%s remaining=%s",
                                request_id,
                                request["telegram_id"],
                                debit[1],
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


def hash_session_token(token: str) -> str:
    """SHA-256 (hex) токена веб-сессии — в БД хранится только он."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class _StoredBooking:
    """Внутреннее состояние брони в ``InMemoryRepository``.

    Отдельный тип от ``ClassBooking``: тот — одноразовый результат вызова
    ``book_class_slot``, а здесь нужен настоящий статус (confirmed/cancelled)
    и момент последнего изменения — без него нельзя ни посчитать занятые
    места, ни проверить дедлайн отмены/кулдаун повторной записи.
    """

    id: int
    status: str
    updated_at: datetime
    # Момент последней записи (для правила отмены после переноса студией).
    booked_at: Optional[datetime] = None


from .studio_memory import InMemoryStudioMixin  # noqa: E402


class InMemoryRepository(InMemoryStudioMixin):
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
        self._class_bookings: Dict[Tuple[int, int], _StoredBooking] = {}
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
        self._web_sessions: Dict[str, Tuple[int, datetime]] = {}
        self._advisory_locks: set[int] = set()
        self._init_studio_state()

    async def initialize(self) -> None:
        logger.warning("Using in-memory storage; data will be lost at shutdown")

    @asynccontextmanager
    async def try_advisory_lock(self, lock_id: int) -> AsyncIterator[bool]:
        if lock_id in self._advisory_locks:
            yield False
            return
        self._advisory_locks.add(lock_id)
        try:
            yield True
        finally:
            self._advisory_locks.discard(lock_id)

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
        self._append_ledger(telegram_id, payment.lessons, "purchase", payment.id)
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
        self._append_ledger(
            payment.telegram_id, -payment.lessons, "refund_reservation", payment_id
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
            row._replace(entry_type="refund")
            if row.payment_id == payment_id and row.entry_type == "refund_reservation"
            else row
            for row in self._credit_ledger
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
        self._append_ledger(
            payment.telegram_id, payment.lessons, "refund_release", payment_id
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

    async def list_pending_lesson_payments_older_than(
        self,
        cutoff: datetime,
        limit: int = 200,
    ) -> Sequence[PendingLessonPayment]:
        items = [
            PendingLessonPayment(
                id=payment.id,
                telegram_id=payment.telegram_id,
                created_at=created_at,
            )
            for payment in self._payments.values()
            if payment.status == "pending"
            and (created_at := self._payment_created_at.get(payment.id)) is not None
            and created_at < cutoff
        ]
        items.sort(key=lambda item: item.created_at)
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
        self._record_slot_event(
            slot.id,
            "created",
            actor_telegram_id=admin_telegram_id,
            new_starts_at=starts_at,
            new_capacity=capacity,
        )
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
        include_cancelled: bool = False,
        starts_after: Optional[datetime] = None,
    ) -> Sequence[ClassSlot]:
        if class_key is not None and class_key not in CLASS_KEYS:
            raise ValueError("Неизвестный формат занятия")
        if not 1 <= limit <= 100:
            raise ValueError("Количество слотов должно быть от 1 до 100")
        after = starts_after or datetime.now(timezone.utc)
        slots = [
            self._slot_with_count(slot)
            for slot in self._class_slots.values()
            if slot.starts_at > after
            and (class_key is None or slot.class_key == class_key)
            and (include_cancelled or slot.status != "cancelled")
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
        notify_user: bool = False,
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
        if previous is not None and previous.status == "confirmed":
            return ClassBooking(
                id=previous.id,
                slot_id=slot_id,
                telegram_id=telegram_id,
                starts_at=slot.starts_at,
                class_key=slot.class_key,
                already_booked=True,
            )
        if previous is not None and previous.status == "cancelled":
            cooldown_ends_at = previous.updated_at + BOOKING_REBOOK_COOLDOWN
            now = datetime.now(timezone.utc)
            if now < cooldown_ends_at:
                hours_left = ceil((cooldown_ends_at - now).total_seconds() / 3600)
                raise BookingCooldownError(
                    "Повторная запись на это занятие после отмены "
                    "будет доступна через {} ч.".format(hours_left)
                )

        current_slot = self._slot_with_count(slot)
        if current_slot.booked_count >= current_slot.capacity:
            raise SlotUnavailableError("На это занятие уже нет свободных мест")

        profile = self._get_profile(telegram_id)
        if profile.lesson_credits <= 0:
            raise InsufficientLessonCreditsError(
                "На балансе нет доступных занятий. Купите абонемент, чтобы записаться."
            )

        source = self._memory_pick_source(telegram_id)
        booking_id = previous.id if previous is not None else self._next_booking_id
        if previous is None:
            self._next_booking_id += 1
        now = datetime.now(timezone.utc)
        self._class_bookings[key] = _StoredBooking(
            id=booking_id,
            status="confirmed",
            updated_at=now,
            booked_at=now,
        )
        balance = profile.lesson_credits - 1
        self._set_credits(telegram_id, balance)
        self._append_ledger(
            telegram_id,
            -1,
            "lesson_use",
            source.id if source is not None and source.kind == "payment" else None,
            grant_id=(
                source.id if source is not None and source.kind == "grant" else None
            ),
            booking_id=booking_id,
        )
        if source is not None:
            source = replace(source, remaining=max(0, source.remaining - 1))
        if notify_user:
            self._memory_enqueue(
                telegram_id,
                "booking_confirmed",
                {
                    "slot_id": slot_id,
                    "class_key": slot.class_key,
                    "starts_at": slot.starts_at.isoformat(),
                    "balance": balance,
                    "source_title": source.title if source else None,
                },
                "booking_confirmed:{}:{}".format(booking_id, uuid.uuid4()),
            )
        self._memory_enqueue_low_balance(telegram_id, balance)
        return ClassBooking(
            id=booking_id,
            slot_id=slot_id,
            telegram_id=telegram_id,
            starts_at=slot.starts_at,
            class_key=slot.class_key,
            balance=balance,
            source=source,
        )

    async def cancel_class_slot_booking(
        self,
        slot_id: int,
        telegram_id: int,
        notify_user: bool = False,
    ) -> bool:
        slot = self._class_slots.get(slot_id)
        if slot is None:
            raise BookingNotFoundError("Запись не найдена")
        key = (slot_id, telegram_id)
        booking = self._class_bookings.get(key)
        if booking is None:
            raise BookingNotFoundError("Запись не найдена")
        if booking.status != "confirmed":
            return False
        check_cancellation_window(
            slot.starts_at, booking.booked_at, slot.rescheduled_at
        )

        self._class_bookings[key] = replace(
            booking, status="cancelled", updated_at=datetime.now(timezone.utc)
        )
        balance = self._get_profile(telegram_id).lesson_credits + 1
        self._set_credits(telegram_id, balance)
        payment_id, grant_id = self._booking_source(booking.id)
        self._append_ledger(
            telegram_id,
            1,
            "adjustment",
            payment_id,
            grant_id=grant_id,
            booking_id=booking.id,
        )
        if notify_user:
            self._memory_enqueue(
                telegram_id,
                "booking_cancelled",
                {
                    "slot_id": slot_id,
                    "class_key": slot.class_key,
                    "starts_at": slot.starts_at.isoformat(),
                    "balance": balance,
                },
                "booking_cancelled:{}:{}".format(booking.id, uuid.uuid4()),
            )
        return True

    async def list_bookings_for_telegram_id(
        self,
        telegram_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[UserBooking]:
        if not 1 <= limit <= 100:
            raise ValueError("Количество записей должно быть от 1 до 100")
        if offset < 0:
            raise ValueError("Смещение списка не может быть отрицательным")
        bookings = []
        for (slot_id, booking_telegram_id), booking in self._class_bookings.items():
            if booking_telegram_id != telegram_id:
                continue
            slot = self._class_slots[slot_id]
            cancelled_by = None
            if booking.status == "cancelled":
                cancelled_by = (
                    "studio"
                    if slot.status == "cancelled"
                    and slot.cancelled_at is not None
                    and booking.updated_at >= slot.cancelled_at
                    else "user"
                )
            moved = next(
                (
                    event
                    for event in reversed(self._slot_events)
                    if event.slot_id == slot_id and event.event_type == "rescheduled"
                ),
                None,
            )
            bookings.append(
                UserBooking(
                    id=booking.id,
                    slot_id=slot_id,
                    class_key=slot.class_key,
                    starts_at=slot.starts_at,
                    booking_status=booking.status,
                    slot_status=slot.status,
                    booked_at=booking.booked_at,
                    cancelled_by=cancelled_by,
                    rescheduled_at=slot.rescheduled_at,
                    previous_starts_at=moved.old_starts_at if moved else None,
                    slot_cancel_reason=slot.cancel_reason,
                )
            )
        bookings.sort(key=lambda item: (item.starts_at, item.id), reverse=True)
        return bookings[offset : offset + limit]

    async def update_class_slot_capacity(
        self,
        slot_id: int,
        capacity: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        if not 1 <= capacity <= 100:
            raise ValueError("Вместимость слота должна быть от 1 до 100")
        slot = self._class_slots.get(slot_id)
        if slot is None:
            return False
        if slot.status == "cancelled":
            raise ValueError("Занятие отменено — вместимость не меняется")
        current = self._slot_with_count(slot)
        if capacity < current.booked_count:
            raise ValueError(
                "Нельзя установить вместимость ниже числа подтверждённых записей"
            )
        self._class_slots[slot_id] = replace(
            slot, capacity=capacity, booked_count=current.booked_count
        )
        if capacity != slot.capacity:
            self._record_slot_event(
                slot_id,
                "capacity_changed",
                actor_telegram_id=admin_telegram_id,
                old_capacity=slot.capacity,
                new_capacity=capacity,
            )
        return True

    async def close_class_slot(
        self,
        slot_id: int,
        admin_telegram_id: Optional[int] = None,
    ) -> bool:
        slot = self._class_slots.get(slot_id)
        if slot is None or slot.status != "open":
            return False
        self._class_slots[slot_id] = replace(slot, status="closed")
        self._record_slot_event(slot_id, "closed", actor_telegram_id=admin_telegram_id)
        return True

    def _slot_with_count(self, slot: ClassSlot) -> ClassSlot:
        booked_count = sum(
            1
            for (booking_slot_id, _), booking in self._class_bookings.items()
            if booking_slot_id == slot.id and booking.status == "confirmed"
        )
        return replace(slot, booked_count=booked_count)

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
            SupportMessage(ticket.id, telegram_id, "user", normalized, created_at=now)
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
            SupportMessage(
                ticket_id,
                admin_telegram_id,
                "admin",
                normalized,
                created_at=datetime.now(timezone.utc),
            )
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
                self._append_ledger(
                    request.telegram_id,
                    -1,
                    "lesson_use",
                    source_payment_id,
                    reference_key="request:{}".format(request_id),
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
            row.delta for row in self._credit_ledger if row.payment_id == payment_id
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

    def _with_profile_name(
        self, user: Optional[WebUserRecord]
    ) -> Optional[WebUserRecord]:
        """Как _WEB_USER_SELECT у PostgreSQL: имя — из профиля бота."""
        if user is None or user.telegram_id not in self._profiles:
            return user
        return replace(user, display_name=self._profiles[user.telegram_id].user_name)

    async def get_web_user_by_id(self, user_id: int) -> Optional[WebUserRecord]:
        return self._with_profile_name(self._web_users.get(user_id))

    async def create_web_session(
        self,
        user_id: int,
        token: str,
        expires_at: datetime,
    ) -> None:
        now = datetime.now(timezone.utc)
        for existing_hash, (existing_user_id, existing_expiry) in list(
            self._web_sessions.items()
        ):
            if existing_user_id == user_id and existing_expiry <= now:
                del self._web_sessions[existing_hash]
        self._web_sessions[hash_session_token(token)] = (user_id, expires_at)

    async def get_web_session_user_id(self, token: str) -> Optional[int]:
        entry = self._web_sessions.get(hash_session_token(token))
        if entry is None:
            return None
        user_id, expires_at = entry
        if expires_at <= datetime.now(timezone.utc):
            return None
        return user_id

    async def delete_web_session(self, token: str) -> None:
        self._web_sessions.pop(hash_session_token(token), None)

    async def get_web_user_by_email(self, email: str) -> Optional[WebUserRecord]:
        normalized_email = email.lower()
        for user in self._web_users.values():
            if user.email is not None and user.email.lower() == normalized_email:
                return self._with_profile_name(user)
        return None

    async def get_web_user_by_telegram_id(
        self,
        telegram_id: int,
    ) -> Optional[WebUserRecord]:
        for user in self._web_users.values():
            if user.telegram_id == telegram_id:
                return self._with_profile_name(user)
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
