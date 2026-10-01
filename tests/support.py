from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
import uuid
from unittest.mock import AsyncMock, Mock

from flamenco_bot.database.repository import (
    DatabaseHealth,
    LessonPayment,
    LessonRequest,
    UserStatistics,
    UserProfile,
)


class FakeMessage:
    def __init__(
        self,
        text="",
        telegram_id=1001,
        full_name="Анна",
        contact=None,
    ):
        self.text = text
        self.from_user = SimpleNamespace(
            id=telegram_id,
            full_name=full_name,
            is_bot=False,
        )
        self.chat = SimpleNamespace(type="private")
        self.contact = contact
        self.answer = AsyncMock()
        self.bot: Any = None

    @property
    def last_answer(self):
        call = self.answer.await_args
        if call is None:
            raise AssertionError("Message.answer was not called")
        return call


class FakeState:
    def __init__(self, data=None):
        self.data = data or {}
        self.current_state = None
        self.clear = AsyncMock(side_effect=self._clear)
        self.set_state = AsyncMock(side_effect=self._set_state)
        self.update_data = AsyncMock(side_effect=self._update_data)
        self.get_data = AsyncMock(side_effect=self._get_data)
        self.get_state = AsyncMock(side_effect=self._get_state)

    async def _clear(self):
        self.current_state = None
        self.data.clear()

    async def _set_state(self, state):
        self.current_state = state.state if hasattr(state, "state") else state

    async def _update_data(self, **kwargs):
        self.data.update(kwargs)
        return self.data

    async def _get_data(self):
        return self.data

    async def _get_state(self):
        return self.current_state


class FakeRepository:
    supports_durable_payments = True

    def __init__(self):
        self.profile = UserProfile(
            telegram_id=1001,
            phone=None,
            user_name="Анна",
            registered_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            is_admin=False,
        )
        self.request = LessonRequest(
            id=7,
            telegram_id=1001,
            kind="booking",
            details="Фламенко для начинающих; пожелания по времени: вечером",
            status="pending",
            created_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
        self.get_or_create_profile = AsyncMock(return_value=self.profile)
        self.initialize = AsyncMock()
        self.close = AsyncMock()
        self.health_check = AsyncMock(
            return_value=DatabaseHealth(
                backend="memory",
                pool_size=0,
                idle_connections=0,
            )
        )
        self.update_phone = AsyncMock()
        self.update_user_name = AsyncMock()
        self.search_profiles = AsyncMock(return_value=[self.profile])
        self.get_profile = AsyncMock(return_value=self.profile)
        self.create_lesson_request = AsyncMock(return_value=self.request)
        self.list_class_slots = AsyncMock(return_value=[])
        self.list_available_class_slots = AsyncMock(return_value=[])
        self.create_class_slot = AsyncMock()
        self.update_class_slot_capacity = AsyncMock(return_value=True)
        self.close_class_slot = AsyncMock(return_value=True)
        self.book_class_slot = AsyncMock()
        self.list_admin_ids = AsyncMock(return_value=[])
        self.create_support_message = AsyncMock(return_value=(1, True))
        self.reply_support_ticket = AsyncMock(return_value=1001)
        self.list_open_support_tickets = AsyncMock(return_value=[])
        self.close_support_ticket = AsyncMock(return_value=1001)
        self.list_pending_requests = AsyncMock(return_value=[self.request])
        self.complete_request = AsyncMock(return_value=True)
        self.record_activity = AsyncMock()
        self.get_user_statistics = AsyncMock(
            return_value=UserStatistics(total_users=10, online_users=2)
        )
        self.create_lesson_payment = AsyncMock(
            return_value=LessonPayment(
                id=8,
                telegram_id=1001,
                package_key="single",
                lessons=1,
                amount_minor=100000,
                provider_payment_id="provider-payment-1",
                confirmation_url="https://pay.example.test/confirm/1",
                status="pending",
            )
        )
        self.begin_lesson_payment_attempt = AsyncMock(
            return_value=SimpleNamespace(
                idempotence_key=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                telegram_id=1001,
                package_key="single",
                package_title="Разовое занятие",
                lessons=1,
                amount_minor=100000,
                status="creating",
                provider_payment_id=None,
                confirmation_url=None,
            )
        )
        self.get_lesson_payment = AsyncMock()
        self.complete_lesson_payment = AsyncMock(return_value=True)
        self.cancel_lesson_payment = AsyncMock()
        self.get_lesson_credits = AsyncMock(return_value=1)
        self.get_scheduled_restart = AsyncMock(return_value=None)
        self.set_scheduled_restart = AsyncMock()
        self.clear_scheduled_restart = AsyncMock()
        self.prepare_lesson_refund = AsyncMock()
        self.record_provider_refund = AsyncMock()
        self.complete_lesson_refund = AsyncMock(return_value=True)


def make_record(
    telegram_id=1001,
    phone=None,
    user_name="Анна",
    is_admin=False,
):
    return {
        "telegram_id": telegram_id,
        "phone": phone,
        "user_name": user_name,
        "registered_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
        "is_admin": is_admin,
        "lesson_credits": 0,
        "id": 7,
        "kind": "booking",
        "details": "тест",
        "status": "pending",
        "created_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
    }


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.applied_migrations = set()
        self.profile_admin_status = {}

    async def execute(self, query, *args):
        self.calls.append((query, args))
        if "INSERT INTO schema_migrations" in query:
            self.applied_migrations.add(args[0])
        return "UPDATE 1"

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "COUNT(*) FILTER (WHERE last_seen_at >= $1)" in query:
            return {"total_users": 1, "online_users": 1}
        is_profile_insert = "INSERT INTO bot_users" in query
        if is_profile_insert:
            is_admin = self.profile_admin_status.setdefault(args[0], args[2])
        else:
            is_admin = False
        return make_record(
            telegram_id=args[0],
            user_name=args[1] if is_profile_insert else "Анна",
            is_admin=is_admin,
        )

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        if "FROM schema_migrations" in query:
            return [{"version": version} for version in sorted(self.applied_migrations)]
        return [make_record()]

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        return 0

    def transaction(self):
        return FakeTransaction()


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        _ = (exc_type, exc, traceback)
        return False


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        _ = (exc_type, exc, traceback)
        return False


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.connection)

    async def close(self):
        return None

    def get_size(self):
        return 1

    def get_idle_size(self):
        return 1


class FakeDispatcher:
    def __init__(self):
        self.update = SimpleNamespace(outer_middleware=Mock())
        self.message = SimpleNamespace(
            middleware=Mock(),
            outer_middleware=Mock(),
        )
        self.callback_query = SimpleNamespace(
            middleware=Mock(),
            outer_middleware=Mock(),
        )
        self.include_router = Mock()
        self.start_polling = AsyncMock()
        self.stop_polling = AsyncMock()

    def __setitem__(self, key, value):
        setattr(self, key, value)
