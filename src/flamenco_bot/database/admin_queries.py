"""Выборки для админ-панели сайта: сводка, аккаунты, платежи, обращения,
показатели базы данных.

Только чтение: изменения (расписание, ответы в поддержку) идут через
существующие методы репозитория и сервисы, как и в админке бота. Отдельный
модуль — только из-за размера repository.py (как studio_postgres.py).
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence


# Как в статистике бота (/stats): «онлайн» — активность за 5 минут.
ONLINE_WINDOW = timedelta(minutes=5)


@dataclass(frozen=True)
class AdminDashboard:
    slots_today: int
    bookings_today: int
    free_seats_today: int
    slots_week: int
    bookings_week: int
    free_seats_week: int
    total_profiles: int
    total_web_users: int
    new_profiles_today: int
    new_web_users_today: int
    online_users: int
    sales_today_count: int
    sales_today_minor: int
    sales_month_count: int
    sales_month_minor: int
    pending_payments: int
    open_tickets: int


@dataclass(frozen=True)
class AdminAccount:
    """Участник глазами администратора: веб-аккаунт и/или профиль бота.

    Одна строка на человека — веб-аккаунт с привязанным Telegram и его
    профиль бота склеены по telegram_id.
    """

    web_user_id: Optional[int]
    email: Optional[str]
    telegram_id: Optional[int]
    name: str
    phone: Optional[str]
    lesson_credits: int
    is_admin: bool
    registered_at: datetime
    last_seen_at: Optional[datetime]


@dataclass(frozen=True)
class AdminPayment:
    id: int
    telegram_id: int
    user_name: Optional[str]
    package_title: str
    lessons: int
    amount_minor: int
    status: str
    created_at: datetime


@dataclass(frozen=True)
class AdminSupportTicket:
    id: int
    telegram_id: int
    user_name: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    last_message: str


@dataclass(frozen=True)
class DatabaseMetrics:
    backend: str
    ping_ms: float
    pool_size: int
    idle_connections: int
    database_size_bytes: Optional[int]
    connections: Optional[int]
    active_web_sessions: int
    notifications_pending: int
    notifications_failed: int


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 200:
        raise ValueError("Количество строк должно быть от 1 до 200")


def _normalize_query(query: str) -> str:
    normalized = query.strip()
    if len(normalized) > 100:
        raise ValueError("Поисковый запрос должен быть не длиннее 100 символов")
    return normalized


class PostgresAdminMixin:
    _pool: Any

    async def get_admin_dashboard(
        self, day_start: datetime, day_end: datetime, week_end: datetime
    ) -> AdminDashboard:
        """Сводка: «сегодня» — [day_start, day_end), «неделя» — [сейчас, week_end)."""
        month_start = day_start - timedelta(days=30)
        online_since = datetime.now(timezone.utc) - ONLINE_WINDOW
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                """
                WITH slot_load AS (
                    SELECT slot.starts_at, slot.capacity, slot.status,
                           (SELECT COUNT(*) FROM lesson_bookings AS booking
                            WHERE booking.slot_id = slot.id
                              AND booking.status = 'confirmed') AS booked
                    FROM lesson_slots AS slot
                    WHERE slot.status <> 'cancelled'
                      AND slot.starts_at >= LEAST($1::TIMESTAMPTZ, NOW())
                      AND slot.starts_at < GREATEST($2::TIMESTAMPTZ, $3::TIMESTAMPTZ)
                ),
                sales AS (
                    SELECT amount_minor, COALESCE(completed_at, created_at) AS paid_at
                    FROM lesson_payments
                    WHERE status IN ('succeeded', 'refund_pending')
                      AND COALESCE(completed_at, created_at) >= $5::TIMESTAMPTZ
                )
                SELECT
                    (SELECT COUNT(*) FROM slot_load
                     WHERE starts_at >= $1 AND starts_at < $2) AS slots_today,
                    (SELECT COALESCE(SUM(booked), 0) FROM slot_load
                     WHERE starts_at >= $1 AND starts_at < $2) AS bookings_today,
                    (SELECT COALESCE(SUM(GREATEST(capacity - booked, 0)), 0)
                     FROM slot_load
                     WHERE status = 'open' AND starts_at >= $1 AND starts_at < $2)
                        AS free_seats_today,
                    (SELECT COUNT(*) FROM slot_load
                     WHERE starts_at >= NOW() AND starts_at < $3) AS slots_week,
                    (SELECT COALESCE(SUM(booked), 0) FROM slot_load
                     WHERE starts_at >= NOW() AND starts_at < $3) AS bookings_week,
                    (SELECT COALESCE(SUM(GREATEST(capacity - booked, 0)), 0)
                     FROM slot_load
                     WHERE status = 'open' AND starts_at >= NOW() AND starts_at < $3)
                        AS free_seats_week,
                    (SELECT COUNT(*) FROM bot_users) AS total_profiles,
                    (SELECT COUNT(*) FROM users) AS total_web_users,
                    (SELECT COUNT(*) FROM bot_users WHERE registered_at >= $1)
                        AS new_profiles_today,
                    (SELECT COUNT(*) FROM users WHERE created_at >= $1)
                        AS new_web_users_today,
                    (SELECT COUNT(*) FROM bot_users WHERE last_seen_at >= $4)
                        AS online_users,
                    (SELECT COUNT(*) FROM sales WHERE paid_at >= $1)
                        AS sales_today_count,
                    (SELECT COALESCE(SUM(amount_minor), 0) FROM sales
                     WHERE paid_at >= $1) AS sales_today_minor,
                    (SELECT COUNT(*) FROM sales) AS sales_month_count,
                    (SELECT COALESCE(SUM(amount_minor), 0) FROM sales)
                        AS sales_month_minor,
                    (SELECT COUNT(*) FROM lesson_payments WHERE status = 'pending')
                        AS pending_payments,
                    (SELECT COUNT(*) FROM support_tickets WHERE status = 'open')
                        AS open_tickets
                """,
                day_start,
                day_end,
                week_end,
                online_since,
                month_start,
            )
        return AdminDashboard(**{key: int(record[key]) for key in record.keys()})

    async def search_admin_accounts(
        self, query: str = "", limit: int = 50
    ) -> Sequence[AdminAccount]:
        normalized = _normalize_query(query)
        _validate_limit(limit)
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT account.id AS web_user_id, account.email,
                       COALESCE(profile.telegram_id, account.telegram_id)
                           AS telegram_id,
                       COALESCE(profile.user_name, account.display_name) AS name,
                       profile.phone,
                       COALESCE(profile.lesson_credits, 0) AS lesson_credits,
                       COALESCE(account.is_admin, FALSE)
                           OR COALESCE(profile.is_admin, FALSE) AS is_admin,
                       LEAST(account.created_at, profile.registered_at)
                           AS registered_at,
                       profile.last_seen_at
                FROM users AS account
                FULL OUTER JOIN bot_users AS profile
                    ON profile.telegram_id = account.telegram_id
                WHERE $1 = ''
                   OR account.email ILIKE $2
                   OR account.display_name ILIKE $2
                   OR profile.user_name ILIKE $2
                   OR profile.phone ILIKE $2
                   OR profile.telegram_id::TEXT = $1
                ORDER BY LEAST(account.created_at, profile.registered_at) DESC
                LIMIT $3
                """,
                normalized,
                "%{}%".format(normalized),
                limit,
            )
        return [AdminAccount(**dict(record)) for record in records]

    async def list_admin_payments(self, limit: int = 50) -> Sequence[AdminPayment]:
        _validate_limit(limit)
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT payment.id, payment.telegram_id, profile.user_name,
                       payment.package_title, payment.lessons,
                       payment.amount_minor, payment.status, payment.created_at
                FROM lesson_payments AS payment
                LEFT JOIN bot_users AS profile
                    ON profile.telegram_id = payment.telegram_id
                ORDER BY payment.created_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [AdminPayment(**dict(record)) for record in records]

    async def list_admin_support_tickets(
        self, status: str = "open", limit: int = 50
    ) -> Sequence[AdminSupportTicket]:
        if status not in {"open", "closed"}:
            raise ValueError("Статус обращения: open или closed")
        _validate_limit(limit)
        async with self._pool.acquire() as connection:
            records = await connection.fetch(
                """
                SELECT ticket.id, ticket.telegram_id, profile.user_name,
                       ticket.status, ticket.created_at, ticket.updated_at,
                       COALESCE(message.body, '') AS last_message
                FROM support_tickets AS ticket
                LEFT JOIN bot_users AS profile
                    ON profile.telegram_id = ticket.telegram_id
                LEFT JOIN LATERAL (
                    SELECT body FROM support_messages
                    WHERE ticket_id = ticket.id
                    ORDER BY created_at DESC, id DESC LIMIT 1
                ) AS message ON TRUE
                WHERE ticket.status = $1
                ORDER BY ticket.updated_at DESC
                LIMIT $2
                """,
                status,
                limit,
            )
        return [AdminSupportTicket(**dict(record)) for record in records]

    async def get_database_metrics(self) -> DatabaseMetrics:
        async with self._pool.acquire() as connection:
            started = time.perf_counter()
            await connection.execute("SELECT 1")
            ping_ms = (time.perf_counter() - started) * 1000
            record = await connection.fetchrow(
                """
                SELECT pg_database_size(current_database()) AS database_size_bytes,
                       (SELECT COUNT(*) FROM pg_stat_activity
                        WHERE datname = current_database()) AS connections,
                       (SELECT COUNT(*) FROM web_sessions WHERE expires_at > NOW())
                           AS active_web_sessions,
                       (SELECT COUNT(*) FROM user_notifications
                        WHERE delivery_status IN ('pending', 'sending'))
                           AS notifications_pending,
                       (SELECT COUNT(*) FROM user_notifications
                        WHERE delivery_status = 'failed') AS notifications_failed
                """
            )
        return DatabaseMetrics(
            backend="postgres",
            ping_ms=round(ping_ms, 2),
            pool_size=self._pool.get_size(),
            idle_connections=self._pool.get_idle_size(),
            database_size_bytes=record["database_size_bytes"],
            connections=record["connections"],
            active_web_sessions=record["active_web_sessions"],
            notifications_pending=record["notifications_pending"],
            notifications_failed=record["notifications_failed"],
        )


class InMemoryAdminMixin:
    """Те же выборки для InMemoryRepository (тесты и запуск без БД)."""

    _profiles: Any
    _web_users: Any
    _web_sessions: Any
    _class_slots: Any
    _payments: Any
    _payment_created_at: Any
    _support_tickets: Any
    _support_messages: Any
    _last_seen: Any
    _notifications: Any

    async def get_admin_dashboard(
        self, day_start: datetime, day_end: datetime, week_end: datetime
    ) -> AdminDashboard:
        now = datetime.now(timezone.utc)
        month_start = day_start - timedelta(days=30)
        slots = [
            self._slot_with_count(slot)
            for slot in self._class_slots.values()
            if slot.status != "cancelled"
        ]
        today = [slot for slot in slots if day_start <= slot.starts_at < day_end]
        week = [slot for slot in slots if now <= slot.starts_at < week_end]
        sales = [
            (payment.amount_minor, self._payment_created_at.get(payment.id, now))
            for payment in self._payments.values()
            if payment.status in {"succeeded", "refund_pending"}
        ]
        sales = [
            (amount, paid_at) for amount, paid_at in sales if paid_at >= month_start
        ]
        online_since = now - ONLINE_WINDOW
        return AdminDashboard(
            slots_today=len(today),
            bookings_today=sum(slot.booked_count for slot in today),
            free_seats_today=sum(
                slot.remaining for slot in today if slot.status == "open"
            ),
            slots_week=len(week),
            bookings_week=sum(slot.booked_count for slot in week),
            free_seats_week=sum(
                slot.remaining for slot in week if slot.status == "open"
            ),
            total_profiles=len(self._profiles),
            total_web_users=len(self._web_users),
            new_profiles_today=sum(
                1
                for profile in self._profiles.values()
                if profile.registered_at >= day_start
            ),
            new_web_users_today=sum(
                1 for user in self._web_users.values() if user.created_at >= day_start
            ),
            online_users=sum(
                1 for seen_at in self._last_seen.values() if seen_at >= online_since
            ),
            sales_today_count=sum(1 for _, paid_at in sales if paid_at >= day_start),
            sales_today_minor=sum(
                amount for amount, paid_at in sales if paid_at >= day_start
            ),
            sales_month_count=len(sales),
            sales_month_minor=sum(amount for amount, _ in sales),
            pending_payments=sum(
                1 for payment in self._payments.values() if payment.status == "pending"
            ),
            open_tickets=sum(
                1
                for ticket in self._support_tickets.values()
                if ticket.status == "open"
            ),
        )

    async def search_admin_accounts(
        self, query: str = "", limit: int = 50
    ) -> Sequence[AdminAccount]:
        normalized = _normalize_query(query).lower()
        _validate_limit(limit)
        accounts = []
        linked = set()
        for user in self._web_users.values():
            profile = self._profiles.get(user.telegram_id)
            if profile is not None:
                linked.add(profile.telegram_id)
            accounts.append(self._admin_account(user, profile))
        for profile in self._profiles.values():
            if profile.telegram_id not in linked:
                accounts.append(self._admin_account(None, profile))

        def matches(account: AdminAccount) -> bool:
            if not normalized:
                return True
            haystack = [account.email or "", account.name, account.phone or ""]
            return any(normalized in value.lower() for value in haystack) or (
                str(account.telegram_id) == normalized
            )

        found = sorted(
            (account for account in accounts if matches(account)),
            key=lambda account: account.registered_at,
            reverse=True,
        )
        return found[:limit]

    def _admin_account(self, user: Any, profile: Any) -> AdminAccount:
        dates = [
            value
            for value in (
                user.created_at if user else None,
                profile.registered_at if profile else None,
            )
            if value is not None
        ]
        telegram_id = profile.telegram_id if profile else user.telegram_id
        return AdminAccount(
            web_user_id=user.id if user else None,
            email=user.email if user else None,
            telegram_id=telegram_id,
            name=profile.user_name if profile else user.display_name,
            phone=profile.phone if profile else None,
            lesson_credits=profile.lesson_credits if profile else 0,
            is_admin=bool((user and user.is_admin) or (profile and profile.is_admin)),
            registered_at=min(dates),
            last_seen_at=self._last_seen.get(telegram_id),
        )

    async def list_admin_payments(self, limit: int = 50) -> Sequence[AdminPayment]:
        _validate_limit(limit)
        now = datetime.now(timezone.utc)
        payments = [
            AdminPayment(
                id=payment.id,
                telegram_id=payment.telegram_id,
                user_name=getattr(
                    self._profiles.get(payment.telegram_id), "user_name", None
                ),
                package_title=payment.package_title,
                lessons=payment.lessons,
                amount_minor=payment.amount_minor,
                status=payment.status,
                created_at=self._payment_created_at.get(payment.id, now),
            )
            for payment in self._payments.values()
        ]
        payments.sort(key=lambda payment: payment.created_at, reverse=True)
        return payments[:limit]

    async def list_admin_support_tickets(
        self, status: str = "open", limit: int = 50
    ) -> Sequence[AdminSupportTicket]:
        if status not in {"open", "closed"}:
            raise ValueError("Статус обращения: open или closed")
        _validate_limit(limit)
        tickets = []
        for ticket in self._support_tickets.values():
            if ticket.status != status:
                continue
            messages = self._support_messages.get(ticket.id, [])
            tickets.append(
                AdminSupportTicket(
                    id=ticket.id,
                    telegram_id=ticket.telegram_id,
                    user_name=getattr(
                        self._profiles.get(ticket.telegram_id), "user_name", None
                    ),
                    status=ticket.status,
                    created_at=ticket.created_at,
                    updated_at=ticket.updated_at,
                    last_message=messages[-1].body if messages else "",
                )
            )
        tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
        return tickets[:limit]

    async def get_database_metrics(self) -> DatabaseMetrics:
        now = datetime.now(timezone.utc)
        statuses = [item["delivery_status"] for item in self._notifications.values()]
        return DatabaseMetrics(
            backend="memory",
            ping_ms=0.0,
            pool_size=0,
            idle_connections=0,
            database_size_bytes=None,
            connections=None,
            active_web_sessions=sum(
                1 for _, expires_at in self._web_sessions.values() if expires_at > now
            ),
            notifications_pending=sum(
                1 for status in statuses if status in {"pending", "sending"}
            ),
            notifications_failed=sum(1 for status in statuses if status == "failed"),
        )
