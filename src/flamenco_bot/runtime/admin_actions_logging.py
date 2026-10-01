import logging
from pathlib import Path
from typing import Optional

from .logging_utils import RetentionRotatingFileHandler
from .paths import PROJECT_ROOT


def create_admin_actions_logger(
    log_directory: Optional[Path] = None,
) -> logging.Logger:
    logger = logging.getLogger("bot.admin_actions")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    target_directory = log_directory or PROJECT_ROOT / "logs"
    target_directory.mkdir(parents=True, exist_ok=True)
    target_file = (target_directory / "admin_actions_log").resolve()
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
