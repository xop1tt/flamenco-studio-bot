"""Импорт админских хендлеров не открывает файлы логов (read-only контейнер)."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LazyAdminActionsLoggerTests(unittest.TestCase):
    def test_import_does_not_create_log_files(self):
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory) / "logs"
            code = (
                "import flamenco_bot.handlers.admin as admin, os, sys;"
                "print(sorted(os.listdir(sys.argv[1])) if os.path.isdir(sys.argv[1]) "
                "else 'no-dir')"
            )
            result = subprocess.run(
                [sys.executable, "-c", code, str(log_dir)],
                capture_output=True,
                text=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
                    "BOT_TOKEN": "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    "BOT_LOG_DIR": str(log_dir),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("admin_actions_log", result.stdout)

    def test_logger_is_created_once_on_first_use(self):
        from flamenco_bot.handlers import admin

        self.assertIs(admin.actions_logger(), admin.actions_logger())


if __name__ == "__main__":
    unittest.main()
