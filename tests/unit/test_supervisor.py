"""Бот и API в одном контейнере (flamenco_bot.supervisor) для Render Free."""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from flamenco_bot import healthcheck, supervisor


SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]
FAIL = [sys.executable, "-c", "raise SystemExit(3)"]


class ChildEnvironmentTests(unittest.TestCase):
    def test_api_listens_on_platform_port(self):
        env = supervisor.child_environment({"PORT": "10000"})
        self.assertEqual(env["API_PORT"], "10000")
        self.assertEqual(env["API_HOST"], "0.0.0.0")
        self.assertEqual(env["BOT_HEARTBEAT_FILE"], supervisor.DEFAULT_HEARTBEAT_FILE)

    def test_explicit_settings_are_kept(self):
        env = supervisor.child_environment(
            {
                "PORT": "10000",
                "API_PORT": "9000",
                "API_HOST": "127.0.0.1",
                "BOT_HEARTBEAT_FILE": "/tmp/custom",
            }
        )
        self.assertEqual(env["API_PORT"], "9000")
        self.assertEqual(env["API_HOST"], "127.0.0.1")
        self.assertEqual(env["BOT_HEARTBEAT_FILE"], "/tmp/custom")

    def test_default_port_without_platform(self):
        self.assertEqual(supervisor.child_environment({})["API_PORT"], "8000")


class KeepaliveSettingsTests(unittest.TestCase):
    def test_render_external_url(self):
        self.assertEqual(
            supervisor.keepalive_url(
                {"RENDER_EXTERNAL_URL": "https://flamenco.onrender.com/"}
            ),
            "https://flamenco.onrender.com/api/health",
        )

    def test_explicit_url_wins(self):
        self.assertEqual(
            supervisor.keepalive_url(
                {
                    "KEEPALIVE_URL": "https://api.example.org/api/health",
                    "RENDER_EXTERNAL_URL": "https://flamenco.onrender.com",
                }
            ),
            "https://api.example.org/api/health",
        )

    def test_no_url_outside_render(self):
        self.assertIsNone(supervisor.keepalive_url({}))

    def test_interval(self):
        self.assertEqual(
            supervisor.keepalive_interval({}),
            supervisor.DEFAULT_KEEPALIVE_INTERVAL_SECONDS,
        )
        self.assertEqual(
            supervisor.keepalive_interval({"KEEPALIVE_INTERVAL_SECONDS": "0"}), 0
        )
        self.assertEqual(
            supervisor.keepalive_interval({"KEEPALIVE_INTERVAL_SECONDS": "300"}), 300
        )

    def test_interval_longer_than_sleep_timeout_is_rejected(self):
        for value in ("900", "30", "-1", "ten"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    supervisor.keepalive_interval({"KEEPALIVE_INTERVAL_SECONDS": value})

    def test_keepalive_requests_until_stopped(self):
        stop = threading.Event()
        calls = []

        def request(url):
            calls.append(url)
            if len(calls) == 2:
                stop.set()
            return 503

        with self.assertLogs("bot.supervisor", level="WARNING"):
            supervisor.run_keepalive(
                "https://x.example/api/health", 0.01, stop, request
            )
        self.assertEqual(calls, ["https://x.example/api/health"] * 2)


class SuperviseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.heartbeat = Path(self.directory.name) / "heartbeat"

    def tearDown(self):
        self.directory.cleanup()

    def test_exits_when_any_process_exits(self):
        stop = threading.Event()
        started = time.monotonic()
        with self.assertLogs("bot.supervisor", level="ERROR") as logs:
            code = supervisor.supervise(
                {"bot": SLEEP, "api": FAIL},
                {},
                self.heartbeat,
                stop,
                poll_seconds=0.05,
            )
        self.assertEqual(code, 1)
        self.assertIn("Process api exited code=3", logs.output[0])
        # Второй процесс остановлен через SIGTERM, а не ждали его 60 секунд.
        self.assertLess(time.monotonic() - started, 10)

    def test_signal_stops_processes_with_zero_code(self):
        stop = threading.Event()
        threading.Timer(0.2, stop.set).start()
        code = supervisor.supervise(
            {"bot": SLEEP, "api": SLEEP},
            {},
            self.heartbeat,
            stop,
            poll_seconds=0.05,
        )
        self.assertEqual(code, 0)

    def test_stale_heartbeat_after_grace_restarts(self):
        stop = threading.Event()
        with self.assertLogs("bot.supervisor", level="ERROR") as logs:
            code = supervisor.supervise(
                {"bot": SLEEP},
                {},
                self.heartbeat,
                stop,
                poll_seconds=0.05,
                startup_grace_seconds=0.1,
            )
        self.assertEqual(code, 1)
        self.assertIn("heartbeat is stale", logs.output[0])

    def test_fresh_heartbeat_keeps_running(self):
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()

        def clock():
            # Heartbeat пишет бот; здесь — тест, перед каждой проверкой.
            healthcheck.write_heartbeat(self.heartbeat)
            return time.monotonic()

        code = supervisor.supervise(
            {"bot": SLEEP},
            {},
            self.heartbeat,
            stop,
            poll_seconds=0.05,
            startup_grace_seconds=0.0,
            clock=clock,
        )
        self.assertEqual(code, 0)

    def test_old_heartbeat_file_is_removed_on_start(self):
        healthcheck.write_heartbeat(self.heartbeat)
        stop = threading.Event()
        stop.set()
        supervisor.supervise({"bot": SLEEP}, {}, self.heartbeat, stop)
        self.assertFalse(self.heartbeat.exists())


if __name__ == "__main__":
    unittest.main()
