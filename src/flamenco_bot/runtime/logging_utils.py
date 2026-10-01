import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


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
            if not backup.name[len(prefix):].isdigit():
                continue
            if not backup.is_file():
                continue
            os.chmod(backup, LOG_FILE_MODE)
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
