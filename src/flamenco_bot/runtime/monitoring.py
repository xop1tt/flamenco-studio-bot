import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol

from ..healthcheck import write_heartbeat
from .bot_logging import UpdateMetrics
from ..database.repository import DatabaseHealth


class HealthRepository(Protocol):
    async def health_check(self) -> DatabaseHealth: ...


async def monitor_health(
    repository: HealthRepository,
    update_metrics: UpdateMetrics,
    logger: logging.Logger,
    interval_seconds: float = 60.0,
    probe_timeout_seconds: float = 5.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    heartbeat_path: Optional[Path] = None,
) -> None:
    if interval_seconds <= 0 or probe_timeout_seconds <= 0:
        raise ValueError("Интервалы мониторинга должны быть положительными")

    while True:
        await sleep(interval_seconds)
        try:
            health = await asyncio.wait_for(
                repository.health_check(),
                timeout=probe_timeout_seconds,
            )
            write_heartbeat(heartbeat_path)
            updates = update_metrics.snapshot()
            logger.info(
                "Health status=ok backend=%s pool_size=%d "
                "pool_idle=%d updates_started=%d updates_succeeded=%d "
                "updates_failed=%d updates_window_seconds=%.0f "
                "updates_avg_ms=%.2f updates_p95_ms=%.2f updates_max_ms=%.2f",
                health.backend,
                health.pool_size,
                health.idle_connections,
                updates.started,
                updates.succeeded,
                updates.failed,
                updates.window_seconds,
                updates.average_duration_ms,
                updates.p95_duration_ms,
                updates.max_duration_ms,
            )
        except Exception as error:
            logger.warning(
                "Health check failed error_type=%s",
                type(error).__name__,
            )
