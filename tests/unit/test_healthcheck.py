"""Docker healthcheck'и (бот, API) и логирование процесса API."""

import io
import logging
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch

from flamenco_bot import healthcheck
from flamenco_bot.api import logging_config
from flamenco_bot.database.repository import DatabaseHealth
from flamenco_bot.runtime.bot_logging import UpdateMetrics
from flamenco_bot.runtime.monitoring import monitor_health


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "heartbeat"

    def tearDown(self):
        self.directory.cleanup()

    def test_fresh_heartbeat_is_healthy(self):
        healthcheck.write_heartbeat(self.path)
        self.assertTrue(healthcheck.heartbeat_is_fresh(self.path))
        self.assertFalse(Path(str(self.path) + ".tmp").exists())

    def test_stale_or_missing_heartbeat_is_unhealthy(self):
        self.assertFalse(healthcheck.heartbeat_is_fresh(self.path))
        self.assertFalse(healthcheck.heartbeat_is_fresh(None))
        healthcheck.write_heartbeat(self.path)
        old = time.time() - healthcheck.HEARTBEAT_MAX_AGE_SECONDS - 5
        os.utime(self.path, (old, old))
        self.assertFalse(healthcheck.heartbeat_is_fresh(self.path))

    def test_bot_command_reads_path_from_environment(self):
        healthcheck.write_heartbeat(self.path)
        with patch.dict(os.environ, {"BOT_HEARTBEAT_FILE": str(self.path)}):
            self.assertEqual(healthcheck.main(["x", "bot"]), 0)
        with patch.dict(os.environ, {"BOT_HEARTBEAT_FILE": ""}):
            self.assertEqual(healthcheck.main(["x", "bot"]), 1)
        self.assertEqual(healthcheck.main(["x"]), 2)


class _HealthHandler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, *args):
        pass


class ApiHealthcheckTests(unittest.TestCase):
    def _serve(self, status):
        handler = type("Handler", (_HealthHandler,), {"status": status})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_api_command_requires_200_from_health_endpoint(self):
        for status, expected in ((200, 0), (503, 1)):
            port = self._serve(status)
            with self.subTest(status=status):
                with patch.dict(os.environ, {"API_PORT": str(port)}):
                    self.assertEqual(healthcheck.main(["x", "api"]), expected)

    def test_api_unreachable_is_unhealthy(self):
        port = self._serve(200)
        with patch.dict(os.environ, {"API_PORT": str(port + 1)}):
            self.assertEqual(healthcheck.main(["x", "api"]), 1)


class MonitorHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def _one_tick(self, repository, path):
        class _Stop(Exception):
            pass

        calls = {"n": 0}

        async def sleep(_seconds):
            calls["n"] += 1
            if calls["n"] > 1:
                raise _Stop

        with self.assertRaises(_Stop):
            await monitor_health(
                repository,
                UpdateMetrics(),
                logging.getLogger("test.monitor"),
                sleep=sleep,
                heartbeat_path=path,
            )

    async def test_heartbeat_written_only_after_successful_database_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "heartbeat"
            failing = AsyncMock()
            failing.health_check.side_effect = ConnectionRefusedError()
            await self._one_tick(failing, path)
            self.assertFalse(path.exists())

            healthy = AsyncMock()
            healthy.health_check.return_value = DatabaseHealth("postgres", 1, 1)
            await self._one_tick(healthy, path)
            self.assertTrue(healthcheck.heartbeat_is_fresh(path))


class ApiLoggingTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("bot")
        self.saved = (
            list(self.logger.handlers),
            self.logger.level,
            self.logger.propagate,
            logging_config._listener,
        )
        logging_config._listener = None

    def tearDown(self):
        if logging_config._listener is not None:
            logging_config._listener.stop()
        handlers, level, propagate, listener = self.saved
        self.logger.handlers = handlers
        self.logger.setLevel(level)
        self.logger.propagate = propagate
        logging_config._listener = listener

    def test_info_and_traceback_reach_stderr_once(self):
        output = io.StringIO()
        with patch.object(logging_config.sys, "stderr", output):
            logging_config.configure_api_logging()
            logging_config.configure_api_logging()  # идемпотентно
            log = logging.getLogger("bot.runtime.payment_reconciliation")
            log.info("Reconciled stale payment payment_id=%s", 42)
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                log.exception("Payment reconciliation iteration failed")
            logging_config._stop_listener()

        text = output.getvalue()
        self.assertIn("INFO bot.runtime.payment_reconciliation", text)
        self.assertIn("payment_id=42", text)
        self.assertIn("Traceback (most recent call last)", text)
        self.assertEqual(text.count("Reconciled stale payment"), 1)
        self.assertEqual(text.count("Traceback"), 1)


if __name__ == "__main__":
    unittest.main()
