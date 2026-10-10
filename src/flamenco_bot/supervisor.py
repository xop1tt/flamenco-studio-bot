"""Telegram-бот и веб-API в одном контейнере.

    python -m flamenco_bot.supervisor

Для хостинга, где бесплатно доступен один постоянно работающий веб-сервис
(Render Free — см. docs/deployment.md, «Бесплатное размещение»). В
compose.yaml бот и API остаются отдельными сервисами, этот модуль там не
используется.

- Запускает ``python -m flamenco_bot`` (polling) и ``python -m
  flamenco_bot.api`` (FastAPI) дочерними процессами с общим stdout/stderr —
  логи обоих видны в журнале платформы.
- API слушает ``0.0.0.0`` на порту ``PORT``, который задаёт платформа.
- Завершается с кодом 1, если любой процесс завершился или heartbeat бота
  устарел (зависание, нет БД): платформа перезапускает контейнер целиком.
  Бот и API работают с одной БД и сами берут advisory-блокировки, поэтому
  повторный запуск безопасен.
- Раз в ``KEEPALIVE_INTERVAL_SECONDS`` запрашивает свой публичный
  ``/api/health`` (``KEEPALIVE_URL``, иначе ``RENDER_EXTERNAL_URL`` от
  Render): бесплатный сервис Render засыпает после 15 минут без входящих
  запросов, а в заснувшем контейнере останавливается и polling бота.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from .healthcheck import HEARTBEAT_ENV, heartbeat_is_fresh


logger = logging.getLogger("bot.supervisor")

DEFAULT_HEARTBEAT_FILE = "/tmp/flamenco-bot-heartbeat"
# Первый heartbeat бот пишет после подключения к БД, миграций и регистрации
# команд; дальше — раз в минуту (runtime/monitoring.py).
STARTUP_GRACE_SECONDS = 300.0
# Render усыпляет сервис после 15 минут без входящих запросов.
DEFAULT_KEEPALIVE_INTERVAL_SECONDS = 600
MAX_KEEPALIVE_INTERVAL_SECONDS = 840
# Render ждёт 30 секунд после SIGTERM — дочерним процессам оставляем 25.
STOP_TIMEOUT_SECONDS = 25.0

PROCESS_COMMANDS = {
    "bot": [sys.executable, "-m", "flamenco_bot"],
    "api": [sys.executable, "-m", "flamenco_bot.api"],
}


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    env = dict(environ)
    env.setdefault("API_HOST", "0.0.0.0")
    if not env.get("API_PORT"):
        env["API_PORT"] = env.get("PORT") or "8000"
    if not env.get(HEARTBEAT_ENV):
        env[HEARTBEAT_ENV] = DEFAULT_HEARTBEAT_FILE
    return env


def keepalive_url(environ: Mapping[str, str]) -> Optional[str]:
    explicit = environ.get("KEEPALIVE_URL", "").strip()
    if explicit:
        return explicit
    external = environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    return external + "/api/health" if external else None


def keepalive_interval(environ: Mapping[str, str]) -> int:
    """Интервал самопроверки в секундах; 0 — выключена."""
    value = environ.get("KEEPALIVE_INTERVAL_SECONDS", "").strip()
    if not value:
        return DEFAULT_KEEPALIVE_INTERVAL_SECONDS
    try:
        seconds = int(value)
    except ValueError as error:
        raise ValueError(
            "KEEPALIVE_INTERVAL_SECONDS должен быть целым числом"
        ) from error
    if seconds != 0 and not 60 <= seconds <= MAX_KEEPALIVE_INTERVAL_SECONDS:
        raise ValueError(
            "KEEPALIVE_INTERVAL_SECONDS должен быть 0 (выключено) или от 60 до "
            "{} — Render усыпляет сервис после 15 минут без запросов".format(
                MAX_KEEPALIVE_INTERVAL_SECONDS
            )
        )
    return seconds


def ping(url: str, timeout_seconds: float = 15.0) -> Optional[int]:
    """HTTP-статус ответа или None, если запрос не удался."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError):
        return None


def run_keepalive(
    url: str,
    interval_seconds: float,
    stop: threading.Event,
    request: Callable[[str], Optional[int]] = ping,
) -> None:
    # Ответ не важен: платформе нужен сам входящий запрос. Неудача — только
    # предупреждение, процессы из-за неё не перезапускаются.
    while not stop.wait(interval_seconds):
        status = request(url)
        if status != 200:
            logger.warning("Keep-alive request failed status=%s", status)


def stop_processes(
    processes: Mapping[str, subprocess.Popen],
    timeout_seconds: float = STOP_TIMEOUT_SECONDS,
) -> None:
    for process in processes.values():
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + timeout_seconds
    for name, process in processes.items():
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            logger.warning("Process %s did not stop in time; killing", name)
            process.kill()
            process.wait()


def supervise(
    commands: Mapping[str, Sequence[str]],
    env: Mapping[str, str],
    heartbeat_path: Optional[Path],
    stop: threading.Event,
    poll_seconds: float = 1.0,
    startup_grace_seconds: float = STARTUP_GRACE_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Код выхода: 0 — остановлен сигналом, 1 — процесс упал или завис."""
    if heartbeat_path is not None:
        # Файл от прошлого запуска не должен считаться свежим heartbeat.
        heartbeat_path.unlink(missing_ok=True)
    processes = {
        name: subprocess.Popen(list(command), env=dict(env))
        for name, command in commands.items()
    }
    started = clock()
    exit_code = 0
    try:
        while not stop.wait(poll_seconds):
            exited = [
                (name, process.returncode)
                for name, process in processes.items()
                if process.poll() is not None
            ]
            if exited:
                for name, returncode in exited:
                    logger.error("Process %s exited code=%s", name, returncode)
                exit_code = 1
                break
            if (
                heartbeat_path is not None
                and clock() - started > startup_grace_seconds
                and not heartbeat_is_fresh(heartbeat_path)
            ):
                logger.error("Bot heartbeat is stale; restarting container")
                exit_code = 1
                break
    finally:
        stop_processes(processes)
    return exit_code


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s supervisor %(message)s",
    )
    env = child_environment(os.environ)
    interval = keepalive_interval(env)
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        logger.info("Received signal %s; stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    url = keepalive_url(env)
    if url and interval:
        threading.Thread(
            target=run_keepalive,
            args=(url, interval, stop),
            name="keepalive",
            daemon=True,
        ).start()
        logger.info("Keep-alive enabled interval=%ss", interval)
    else:
        logger.info("Keep-alive disabled")

    heartbeat = Path(env[HEARTBEAT_ENV])
    logger.info("Starting bot and api port=%s", env["API_PORT"])
    exit_code = supervise(PROCESS_COMMANDS, env, heartbeat, stop)
    stop.set()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
