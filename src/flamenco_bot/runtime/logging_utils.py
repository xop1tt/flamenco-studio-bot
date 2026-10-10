import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .paths import get_log_directory


LOG_RETENTION_DAYS = 30
LOG_FILE_MODE = 0o600


class RetentionRotatingFileHandler(RotatingFileHandler):
    def __init__(self, filename: Path, **kwargs):
        self.retention_seconds = LOG_RETENTION_DAYS * 24 * 60 * 60
        super().__init__(filename, **kwargs)
        os.chmod(self.baseFilename, LOG_FILE_MODE)
        self._remove_expired_backups()

    def doRollover(self):
        super().doRollover()
        self._remove_expired_backups()

    def _remove_expired_backups(self):
        cutoff = time.time() - self.retention_seconds
        base_path = Path(self.baseFilename)
        prefix = base_path.name + "."
        for backup in base_path.parent.glob(prefix + "*"):
            if not backup.name[len(prefix) :].isdigit():
                continue
            if not backup.is_file():
                continue
            os.chmod(backup, LOG_FILE_MODE)
            if backup.stat().st_mtime < cutoff:
                backup.unlink()


def create_file_logger(
    name: str, file_name: str, log_directory: Optional[Path] = None
) -> logging.Logger:
    """Отдельный журнал в файле каталога логов (не в общем потоке).

    Повторный вызов не добавляет второй обработчик на тот же файл.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    target_directory = log_directory or get_log_directory()
    target_directory.mkdir(parents=True, exist_ok=True)
    target_file = (target_directory / file_name).resolve()
    if not any(
        getattr(handler, "baseFilename", None) == str(target_file)
        for handler in logger.handlers
    ):
        handler = RetentionRotatingFileHandler(
            target_file,
            encoding="utf-8",
            maxBytes=5_000_000,
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)

    return logger


def create_admin_actions_logger(
    log_directory: Optional[Path] = None,
) -> logging.Logger:
    return create_file_logger("bot.admin_actions", "admin_actions_log", log_directory)
