import errno
import socket
import ssl
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from flamenco_bot.database.repository import (
    DatabaseUnavailableError,
    MIGRATIONS_DIRECTORY,
    InMemoryRepository,
    PostgresRepository,
    is_database_configured,
)
from tests.support import FakePool


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pool = FakePool()
        self.repository = PostgresRepository(self.pool)

    async def test_profile_operations_use_parameterized_queries(self):
        profile = await self.repository.get_or_create_profile(1001, "Анна", False)
        self.assertEqual(profile.telegram_id, 1001)
        await self.repository.update_phone(1001, "+79990000000")
        await self.repository.update_user_name(1001, "Новое имя")
        update_queries = self.pool.connection.calls[1:]
        self.assertEqual(update_queries[0][1], (1001, "+79990000000"))
        self.assertEqual(update_queries[1][1], (1001, "Новое имя"))

    async def test_profile_load_preserves_admin_status_set_in_database(self):
        self.pool.connection.profile_admin_status[1001] = True

        profile = await self.repository.get_or_create_profile(1001, "Анна", False)

        self.assertTrue(profile.is_admin)
        query, _ = self.pool.connection.calls[-1]
        self.assertIn("SET is_admin = bot_users.is_admin", query)
        self.assertNotIn("EXCLUDED.is_admin", query)

    async def test_profile_search_and_exact_lookup(self):
        profiles = await self.repository.search_profiles("Анна", limit=10)
        self.assertEqual(profiles[0].telegram_id, 1001)
        query, args = self.pool.connection.calls[-1]
        self.assertIn("user_name ILIKE $2", query)
        self.assertEqual(args, ("Анна", "%Анна%", 10))

        profile = await self.repository.get_profile(1001)
        if profile is None:
            self.fail("Profile lookup returned no profile")
        self.assertEqual(profile.telegram_id, 1001)
        query, args = self.pool.connection.calls[-1]
        self.assertIn("WHERE telegram_id = $1", query)
        self.assertEqual(args, (1001,))

        with self.assertRaises(ValueError):
            await self.repository.search_profiles("")
        with self.assertRaises(ValueError):
            await self.repository.search_profiles("x", limit=101)

    async def test_request_operations_and_validation(self):
        request = await self.repository.create_lesson_request(
            1001,
            "booking",
            "вечером",
        )
        self.assertEqual(request.id, 7)
        self.assertEqual(len(await self.repository.list_pending_requests()), 1)
        self.assertTrue(await self.repository.complete_request(7))
        with self.assertRaises(ValueError):
            await self.repository.create_lesson_request(1001, "invalid", "x")
        with self.assertRaises(ValueError):
            await self.repository.list_pending_requests(101)

    async def test_connect_requires_database_url(self):
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            await PostgresRepository.connect("")

    async def test_connect_rejects_documentation_placeholder_hostname(self):
        with self.assertRaisesRegex(ValueError, "примерный hostname"):
            await PostgresRepository.connect(
                "postgresql://bot@db.example.com:5432/flamenco_bot"
            )

    async def test_connect_reports_refused_local_postgres_without_connection_details(self):
        with patch(
            "flamenco_bot.database.repository.asyncpg.create_pool",
            new=AsyncMock(
                side_effect=OSError(errno.ECONNREFUSED, "Connection refused")
            ),
        ):
            with self.assertRaisesRegex(
                DatabaseUnavailableError,
                "сервер запущен",
            ):
                await PostgresRepository.connect(
                    "postgresql://bot:private-password@localhost:5432/bot",
                    ssl_mode="disable",
                    allow_insecure_local=True,
                )

    async def test_connect_reports_postgres_hostname_resolution_failure(self):
        with patch(
            "flamenco_bot.database.repository.asyncpg.create_pool",
            new=AsyncMock(
                side_effect=socket.gaierror(socket.EAI_NONAME, "Name or service not known")
            ),
        ):
            with self.assertRaisesRegex(
                DatabaseUnavailableError,
                "разрешить hostname",
            ):
                await PostgresRepository.connect(
                    "postgresql://bot@db.invalid:5432/bot",
                )

    async def test_connect_enforces_verified_tls_without_connecting(self):
        pool = FakePool()
        with patch(
            "flamenco_bot.database.repository.asyncpg.create_pool",
            new=AsyncMock(return_value=pool),
        ) as create_pool:
            repository = await PostgresRepository.connect(
                "postgresql://bot@db.test.internal/bot"
            )

        self.assertIs(repository._pool, pool)
        create_pool.assert_awaited_once()
        pool_call = create_pool.await_args
        if pool_call is None:
            self.fail("PostgreSQL pool was not constructed")
        self.assertEqual(pool_call.kwargs["min_size"], 1)
        self.assertEqual(pool_call.kwargs["max_size"], 10)
        ssl_context = pool_call.kwargs["ssl"]
        self.assertIsInstance(ssl_context, ssl.SSLContext)
        self.assertEqual(ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ssl_context.check_hostname)

    async def test_development_can_disable_tls_for_loopback_database_only(self):
        pool = FakePool()
        with patch(
            "flamenco_bot.database.repository.asyncpg.create_pool",
            new=AsyncMock(return_value=pool),
        ) as create_pool:
            await PostgresRepository.connect(
                "postgresql://bot@localhost:5432/bot",
                ssl_mode="disable",
                allow_insecure_local=True,
            )

        pool_call = create_pool.await_args
        if pool_call is None:
            self.fail("PostgreSQL pool was not constructed")
        self.assertIs(pool_call.kwargs["ssl"], False)

    async def test_disabling_tls_is_rejected_for_remote_or_production_database(self):
        with self.assertRaisesRegex(ValueError, "только для localhost"):
            await PostgresRepository.connect(
                "postgresql://bot@db.example.net:5432/bot",
                ssl_mode="disable",
                allow_insecure_local=True,
            )
        with self.assertRaisesRegex(ValueError, "только для localhost"):
            await PostgresRepository.connect(
                "postgresql://bot@localhost:5432/bot",
                ssl_mode="disable",
                allow_insecure_local=False,
            )

    async def test_database_health_check_executes_probe_and_reports_pool(self):
        health = await self.repository.health_check()

        self.assertEqual(
            health.backend,
            "postgres",
        )
        self.assertEqual((health.pool_size, health.idle_connections), (1, 1))
        self.assertEqual(self.pool.connection.calls[-1], ("SELECT 1", ()))

    async def test_schema_initialize_and_pool_close(self):
        await self.repository.initialize()
        migration_calls = [
            query for query, _ in self.pool.connection.calls
            if "CREATE TABLE IF NOT EXISTS bot_users" in query
        ]
        self.assertEqual(len(migration_calls), 1)
        await self.repository.initialize()
        migration_calls = [
            query for query, _ in self.pool.connection.calls
            if "CREATE TABLE IF NOT EXISTS bot_users" in query
        ]
        self.assertEqual(len(migration_calls), 1)
        self.assertEqual(self.pool.connection.applied_migrations, {"001", "002"})
        await self.repository.close()

    async def test_schema_protects_profile_identity_and_request_states(self):
        migration = (MIGRATIONS_DIRECTORY / "001_initial_schema.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("telegram_id BIGINT PRIMARY KEY", migration)
        self.assertIn("CHECK (kind IN ('booking', 'purchase'))", migration)
        self.assertIn("REFERENCES bot_users", migration)

    async def test_runtime_payment_migration_tracks_activity_and_paid_credits(self):
        migration = (MIGRATIONS_DIRECTORY / "002_runtime_and_payments.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("last_seen_at", migration)
        self.assertIn("lesson_credits", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS lesson_payments", migration)

    async def test_database_configuration_detects_missing_and_placeholder_urls(self):
        self.assertFalse(is_database_configured(""))
        self.assertFalse(
            is_database_configured("postgresql://bot@db.example.com/flamenco_bot")
        )
        self.assertTrue(
            is_database_configured(
                "postgresql://bot@db.studio.internal/flamenco_bot"
            )
        )

    async def test_in_memory_repository_supports_profiles_and_requests(self):
        repository = InMemoryRepository()
        profile = await repository.get_or_create_profile(1001, "Анна", False)
        self.assertEqual(profile.user_name, "Анна")
        await repository.update_phone(1001, "+79990000000")
        await repository.update_user_name(1001, "Анна Мария")
        updated = await repository.get_or_create_profile(1001, "Ignored", False)
        self.assertEqual(updated.phone, "+79990000000")
        self.assertEqual(updated.user_name, "Анна Мария")
        self.assertFalse(updated.is_admin)

        request = await repository.create_lesson_request(1001, "booking", "вечером")
        self.assertEqual(request.id, 1)
        self.assertEqual(len(await repository.list_pending_requests()), 1)
        self.assertTrue(await repository.complete_request(1))
        self.assertEqual(await repository.list_pending_requests(), [])
        await repository.close()

    async def test_in_memory_payment_adds_credits_only_once_and_tracks_activity(self):
        repository = InMemoryRepository()
        await repository.get_or_create_profile(1001, "Анна", False)
        payment = await repository.create_lesson_payment(
            telegram_id=1001,
            package_key="pack_4",
            lessons=4,
            amount_minor=360000,
            provider_payment_id="provider-payment",
            confirmation_url="https://pay.example.test",
        )

        self.assertTrue(
            await repository.complete_lesson_payment(payment.id, 1001)
        )
        self.assertFalse(
            await repository.complete_lesson_payment(payment.id, 1001)
        )
        self.assertEqual(await repository.get_lesson_credits(1001), 4)
        await repository.record_activity(1001)
        stats = await repository.get_user_statistics(
            datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        self.assertEqual((stats.total_users, stats.online_users), (1, 1))
