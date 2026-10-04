"""Docker healthcheck'и бота и веб-API — только стандартная библиотека.

    python -m flamenco_bot.healthcheck bot   # свежий heartbeat бота
    python -m flamenco_bot.healthcheck api   # GET /api/health отвечает 200

Бот обновляет heartbeat-файл (``BOT_HEARTBEAT_FILE``) после каждой успешной
проверки PostgreSQL в ``runtime/monitoring.py`` (раз в минуту): файл
устаревает, если зависли event loop или БД. API считается живым, только если
``/api/health`` отвечает 200 — при недоступной БД он отдаёт 503.
"""

import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

HEARTBEAT_ENV = "BOT_HEARTBEAT_FILE"
# Проверка БД идёт раз в 60 с: три пропуска подряд — процесс нездоров.
HEARTBEAT_MAX_AGE_SECONDS = 180.0


def heartbeat_path_from_env() -> Optional[Path]:
    value = os.getenv(HEARTBEAT_ENV, "").strip()
    return Path(value) if value else None


def write_heartbeat(path: Optional[Path]) -> None:
    """Атомарная запись (временный файл + rename): healthcheck не прочитает
    наполовину записанный файл."""
    if path is None:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("{:.0f}\n".format(time.time()), encoding="utf-8")
    os.replace(temporary, path)


def heartbeat_is_fresh(
    path: Optional[Path], max_age_seconds: float = HEARTBEAT_MAX_AGE_SECONDS
) -> bool:
    if path is None:
        return False
    try:
        return time.time() - path.stat().st_mtime <= max_age_seconds
    except OSError:
        return False


def api_is_healthy(url: str, timeout_seconds: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def main(argv: list[str]) -> int:
    target = argv[1] if len(argv) > 1 else ""
    if target == "bot":
        return 0 if heartbeat_is_fresh(heartbeat_path_from_env()) else 1
    if target == "api":
        port = os.getenv("API_PORT", "8000")
        return 0 if api_is_healthy("http://127.0.0.1:{}/api/health".format(port)) else 1
    print("usage: python -m flamenco_bot.healthcheck bot|api", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
