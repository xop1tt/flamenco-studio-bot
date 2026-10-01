import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_log_directory() -> Path:
    configured_directory = os.getenv("BOT_LOG_DIR")
    if configured_directory:
        return Path(configured_directory).expanduser()
    return PROJECT_ROOT / "logs"
