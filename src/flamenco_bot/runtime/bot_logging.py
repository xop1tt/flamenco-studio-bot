import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque, Optional, Tuple

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from .logging_utils import RetentionRotatingFileHandler
from .paths import get_log_directory


HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class UpdateMetricsSnapshot:
    started: int
    succeeded: int
    failed: int
    total_duration_ms: float
    max_duration_ms: float
    average_duration_ms: float
    p95_duration_ms: float
    window_seconds: float


class UpdateMetrics:
    def __init__(
        self,
        window_seconds: float = 300.0,
        max_samples: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_seconds <= 0 or max_samples < 1:
            raise ValueError("Окно и лимит метрик должны быть положительными")
        self.window_seconds = window_seconds
        self.clock = clock
        self._samples: Deque[Tuple[float, float, bool]] = deque(maxlen=max_samples)

    def record(self, duration_ms: float, failed: bool) -> None:
        if duration_ms < 0:
            raise ValueError("Длительность обновления не может быть отрицательной")
        now = self.clock()
        self._discard_expired(now)
        self._samples.append((now, duration_ms, failed))

    def snapshot(self) -> UpdateMetricsSnapshot:
        self._discard_expired(self.clock())
        count = len(self._samples)
        durations = sorted(sample[1] for sample in self._samples)
        total_duration_ms = sum(durations)
        p95_index = max(0, (95 * count + 99) // 100 - 1)
        return UpdateMetricsSnapshot(
            started=count,
            succeeded=sum(not sample[2] for sample in self._samples),
            failed=sum(sample[2] for sample in self._samples),
            total_duration_ms=total_duration_ms,
            max_duration_ms=max(durations, default=0.0),
            average_duration_ms=total_duration_ms / count if count else 0.0,
            p95_duration_ms=durations[p95_index] if durations else 0.0,
            window_seconds=self.window_seconds,
        )

    def _discard_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()


class UpdateLoggingMiddleware(BaseMiddleware):
    def __init__(
        self,
        logger: logging.Logger,
        metrics: Optional[UpdateMetrics] = None,
    ) -> None:
        self.logger = logger
        self.metrics = metrics

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender = getattr(event, "from_user", None)
        if sender is None:
            update_event = getattr(event, "event", None)
            sender = getattr(update_event, "from_user", None)
        telegram_id = sender.id if sender else None
        handler_name = getattr(handler, "__name__", handler.__class__.__name__)
        self.logger.info(
            "Update started handler=%s event=%s telegram_id=%s",
            handler_name,
            event.__class__.__name__,
            telegram_id,
        )
        started_at = time.perf_counter()
        try:
            repository = data.get("repository")
            if sender is not None and repository is not None:
                await repository.record_activity(sender.id)
            result = await handler(event, data)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            if self.metrics is not None:
                self.metrics.record(duration_ms, failed=True)
            self.logger.exception(
                "Update failed handler=%s telegram_id=%s",
                handler_name,
                telegram_id,
            )
            raise
        duration_ms = (time.perf_counter() - started_at) * 1000
        if self.metrics is not None:
            self.metrics.record(duration_ms, failed=False)
        self.logger.info(
            "Update completed handler=%s telegram_id=%s duration_ms=%.2f",
            handler_name,
            telegram_id,
            duration_ms,
        )
        return result


def configure_logging(log_directory: Optional[Path] = None) -> logging.Logger:
    directory = log_directory or get_log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(
        getattr(handler, "_flamenco_bot_console_handler", False)
        for handler in root_logger.handlers
    ):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        console_handler._flamenco_bot_console_handler = True
        root_logger.addHandler(console_handler)

    if not any(
        getattr(handler, "baseFilename", None) == str((directory / "bot.log").resolve())
        for handler in root_logger.handlers
    ):
        handler = RetentionRotatingFileHandler(
            directory / "bot.log",
            encoding="utf-8",
            maxBytes=10_000_000,
            backupCount=5,
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root_logger.addHandler(handler)

    logging.getLogger("aiogram").setLevel(logging.INFO)
    logger = logging.getLogger("bot")
    logger.info("Logging configured; logs directory=%s", directory)
    return logger
