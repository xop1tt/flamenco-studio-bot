import os
import time
import unittest
from datetime import datetime, timedelta, timezone

import asyncpg

from flamenco_bot.database.repository import PostgresRepository


DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    DATABASE_URL,
    "TEST_DATABASE_URL is not set; configure a dedicated test PostgreSQL database",
)
class PostgresIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.admin_pool = await asyncpg.create_pool(DATABASE_URL)
        self.pool = None
        self.repository = None
        self.schema = "test_bot_{}_{}".format(os.getpid(), time.time_ns())
        self.telegram_id = time.time_ns()
        try:
            async with self.admin_pool.acquire() as connection:
                await connection.execute('CREATE SCHEMA "{}"'.format(self.schema))
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                server_settings={"search_path": self.schema},
            )
            async with self.pool.acquire() as connection:
                await connection.execute(
                    """
                    CREATE TABLE bot_users (
                        telegram_id BIGINT PRIMARY KEY CHECK (telegram_id > 0),
                        phone TEXT,
                        user_name TEXT NOT NULL,
                        registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        is_admin BOOLEAN NOT NULL DEFAULT FALSE
                    );

                    CREATE TABLE lesson_requests (
                        id BIGSERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL
                            REFERENCES bot_users(telegram_id) ON DELETE CASCADE,
                        kind TEXT NOT NULL
                            CHECK (kind IN ('booking', 'purchase')),
                        details TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'completed')),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
            self.repository = PostgresRepository(self.pool)
            await self.repository.initialize()
            await self.repository.get_or_create_profile(
                self.telegram_id,
                "Integration test",
                False,
            )
        except BaseException:
            await self._cleanup()
            raise

    async def asyncTearDown(self):
        await self._cleanup()

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise AssertionError("PostgreSQL test pool was not initialized")
        return self.pool

    def _require_repository(self) -> PostgresRepository:
        if self.repository is None:
            raise AssertionError("PostgreSQL test repository was not initialized")
        return self.repository

    async def _cleanup(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
        try:
            if getattr(self, "schema", None) and self.admin_pool is not None:
                async with self.admin_pool.acquire() as connection:
                    await connection.execute(
                        'DROP SCHEMA IF EXISTS "{}" CASCADE'.format(self.schema)
                    )
        finally:
            if self.admin_pool is not None:
                await self.admin_pool.close()
                self.admin_pool = None

    async def test_migration_upgrades_legacy_schema_and_repository_queries_work(self):
        pool = self._require_pool()
        repository = self._require_repository()
        async with pool.acquire() as connection:
            versions = await connection.fetch(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            index_name = await connection.fetchval(
                "SELECT to_regclass('lesson_requests_pending_created_idx')"
            )
        self.assertEqual(
            [record["version"] for record in versions],
            ["001", "002"],
        )
        self.assertEqual(index_name, "lesson_requests_pending_created_idx")

        await repository.initialize()
        request = await repository.create_lesson_request(
            self.telegram_id,
            "booking",
            "integration test request",
        )
        profiles = await repository.search_profiles(
            "Integration test",
            limit=10,
        )
        pending = await repository.list_pending_requests()

        self.assertTrue(
            any(profile.telegram_id == self.telegram_id for profile in profiles)
        )
        self.assertIn(request.id, [item.id for item in pending])
        self.assertTrue(await repository.complete_request(request.id))

        payment = await repository.create_lesson_payment(
            telegram_id=self.telegram_id,
            package_key="pack_4",
            lessons=4,
            amount_minor=360000,
            provider_payment_id="integration-payment-{}".format(self.telegram_id),
            confirmation_url="https://example.test/payment",
        )
        self.assertTrue(
            await repository.complete_lesson_payment(payment.id, self.telegram_id)
        )
        self.assertFalse(
            await repository.complete_lesson_payment(payment.id, self.telegram_id)
        )
        self.assertEqual(await repository.get_lesson_credits(self.telegram_id), 4)

        await repository.record_activity(self.telegram_id)
        statistics = await repository.get_user_statistics(
            datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        self.assertEqual((statistics.total_users, statistics.online_users), (1, 1))
