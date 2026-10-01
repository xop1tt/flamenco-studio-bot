import asyncio
import logging
from typing import Awaitable, Callable, Protocol

from .bot_logging import UpdateMetrics
from ..database.repository import DatabaseHealth


class HealthRepository(Protocol):
    async def health_check(self) -> DatabaseHealth:
        ...


async def monitor_health(
    repository: HealthRepository,
    update_metrics: UpdateMetrics,
    logger: logging.Logger,
    interval_seconds: float = 60.0,
    probe_timeout_seconds: float = 5.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
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
            updates = update_metrics.snapshot()
            logger.info(
                "Health status=ok backend=%s pool_size=%d "
                "pool_idle=%d updates_started=%d updates_succeeded=%d "
                "updates_failed=%d updates_total_ms=%.2f updates_max_ms=%.2f",
                health.backend,
                health.pool_size,
                health.idle_connections,
                updates.started,
                updates.succeeded,
                updates.failed,
                updates.total_duration_ms,
                updates.max_duration_ms,
            )
        except Exception as error:
            logger.warning(
                "Health check failed error_type=%s",
                type(error).__name__,
            )
