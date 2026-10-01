import asyncio
import logging
import os
import sys
from time import monotonic
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional
from os import walk


logger = logging.getLogger("bot.lifecycle")
RESTART_NOTICE = "бот будет перезапущен через час"
CODE_CHECK_INTERVAL_SECONDS = 30
CODE_CHANGE_RESTART_DELAY_SECONDS = 60 * 60
EXCLUDED_CODE_PATHS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "tests",
    "logs",
    "htmlcov",
}


def code_snapshot(root: Path) -> Dict[str, tuple[int, int]]:
    snapshot: Dict[str, tuple[int, int]] = {}
    for current_directory, subdirectories, filenames in walk(root):
        subdirectories[:] = [
            name
            for name in subdirectories
            if name not in EXCLUDED_CODE_PATHS and not name.startswith(".")
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(current_directory) / filename
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            snapshot[str(path.relative_to(root))] = (
                stat.st_mtime_ns,
                stat.st_size,
            )
    return snapshot


def next_local_midnight(now: datetime) -> datetime:
    tomorrow = now.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=now.tzinfo)


class RestartController:
    def __init__(
        self,
        bot: Any,
        dispatcher: Any,
        admins: list[int],
        logger: logging.Logger,
        source_root: Path,
        check_interval: float = CODE_CHECK_INTERVAL_SECONDS,
        code_restart_delay: float = CODE_CHANGE_RESTART_DELAY_SECONDS,
        clock: Callable[[], datetime] = datetime.now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        wait_for: Callable[..., Awaitable[Any]] = asyncio.wait_for,
        restart_store: Optional[Any] = None,
    ) -> None:
        self.bot = bot
        self.dispatcher = dispatcher
        self.admins = tuple(admins)
        self.logger = logger
        self.source_root = source_root
        self.check_interval = check_interval
        self.code_restart_delay = code_restart_delay
        self.clock = clock
        self.sleep = sleep
        self.wait_for = wait_for
        self.restart_store = restart_store
        self.restart_event = asyncio.Event()
        self.restart_reason: Optional[str] = None
        self.polling_started = False
        self.stop_polling_task: Optional[asyncio.Task[None]] = None
        self.scheduled_restart_at: Optional[datetime] = None
        self.scheduled_restart_task: Optional[asyncio.Task[None]] = None
        self.started_at = monotonic()

    async def notify_admins(self, text: str) -> None:
        for admin_id in self.admins:
            try:
                await self.bot.send_message(chat_id=admin_id, text=text)
            except Exception:
                self.logger.exception(
                    "Failed to send bot lifecycle notification admin_id=%s",
                    admin_id,
                )

    async def request_restart(self, reason: str) -> None:
        if self.restart_event.is_set():
            return
        self.restart_reason = reason
        self.restart_event.set()
        self.logger.warning("Bot restart requested reason=%s", reason)
        self._schedule_polling_stop()

    async def schedule_restart(self, scheduled_at: datetime) -> datetime:
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.astimezone()
        scheduled_at = scheduled_at.astimezone()
        if scheduled_at <= self.clock().astimezone():
            raise ValueError("Время перезапуска должно быть в будущем")

        await self.cancel_scheduled_restart()
        if self.restart_store is not None:
            await self.restart_store.set_scheduled_restart(scheduled_at)
        self.scheduled_restart_at = scheduled_at
        self.scheduled_restart_task = asyncio.create_task(
            self._wait_for_scheduled_restart(scheduled_at)
        )
        self.logger.info("Bot restart scheduled at=%s", scheduled_at.isoformat())
        return scheduled_at

    async def cancel_scheduled_restart(self) -> bool:
        task = self.scheduled_restart_task
        canceled = task is not None or self.scheduled_restart_at is not None
        if task is not None:
            self.scheduled_restart_task = None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.scheduled_restart_at = None
        if self.restart_store is not None:
            await self.restart_store.clear_scheduled_restart()
        if canceled:
            self.logger.info("Scheduled bot restart cancelled")
        return canceled

    async def restore_scheduled_restart(self) -> Optional[datetime]:
        if self.restart_store is None:
            return None
        scheduled_at = await self.restart_store.get_scheduled_restart()
        if scheduled_at is None:
            return None
        if scheduled_at <= self.clock().astimezone():
            await self.restart_store.clear_scheduled_restart()
            self.logger.warning(
                "Discarded expired scheduled restart at=%s",
                scheduled_at.isoformat(),
            )
            return None
        return await self.schedule_restart(scheduled_at)

    async def _wait_for_scheduled_restart(self, scheduled_at: datetime) -> None:
        if self.restart_event.is_set():
            return
        delay = max(
            0.0,
            (scheduled_at - self.clock().astimezone()).total_seconds(),
        )
        try:
            await self.wait_for(self.restart_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            await self.request_restart("admin_scheduled")
        finally:
            if self.scheduled_restart_at == scheduled_at:
                self.scheduled_restart_task = None
                self.scheduled_restart_at = None

    async def notify_critical_error(self, error: Exception) -> None:
        if self.restart_event.is_set():
            return
        self.restart_reason = "critical_error"
        self.restart_event.set()
        self.logger.error(
            "Critical bot error; restarting immediately error_type=%s",
            type(error).__name__,
        )
        await self.notify_admins(
            "Критическая ошибка бота ({}). Бот будет перезапущен.".format(
                type(error).__name__
            )
        )
        self._schedule_polling_stop()

    def _schedule_polling_stop(self) -> None:
        if (
            self.polling_started
            and self.dispatcher is not None
            and (self.stop_polling_task is None or self.stop_polling_task.done())
        ):
            self.stop_polling_task = asyncio.create_task(self.dispatcher.stop_polling())

    async def close(self) -> None:
        if self.scheduled_restart_task is not None:
            task = self.scheduled_restart_task
            self.scheduled_restart_task = None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.stop_polling_task is not None:
            await asyncio.gather(self.stop_polling_task, return_exceptions=True)

    async def watch_code_changes(self) -> None:
        previous_snapshot = code_snapshot(self.source_root)
        while not self.restart_event.is_set():
            await self.sleep(self.check_interval)
            current_snapshot = code_snapshot(self.source_root)
            if current_snapshot == previous_snapshot:
                continue

            changed_files = sorted(
                path
                for path in set(previous_snapshot) | set(current_snapshot)
                if previous_snapshot.get(path) != current_snapshot.get(path)
            )
            self.logger.warning(
                "Bot code change detected files=%s",
                ", ".join(changed_files),
            )
            await self.notify_admins(RESTART_NOTICE)
            try:
                await self.wait_for(
                    self.restart_event.wait(),
                    timeout=self.code_restart_delay,
                )
            except asyncio.TimeoutError:
                await self.request_restart("code_changed")
            return

    async def schedule_midnight_restart(self) -> None:
        now = self.clock().astimezone()
        midnight = next_local_midnight(now)
        reminder_time = midnight - timedelta(hours=1)
        reminder_delay = max(0.0, (reminder_time - now).total_seconds())
        try:
            await self.wait_for(
                self.restart_event.wait(),
                timeout=reminder_delay,
            )
            return
        except asyncio.TimeoutError:
            pass

        await self.notify_admins(RESTART_NOTICE)
        until_midnight = max(
            0.0, (midnight - self.clock().astimezone()).total_seconds()
        )
        try:
            await self.wait_for(
                self.restart_event.wait(),
                timeout=until_midnight,
            )
        except asyncio.TimeoutError:
            await self.request_restart("daily_midnight")

    async def run_lifecycle_task(
        self,
        task_name: str,
        task_factory: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            await task_factory()
        except Exception as error:
            self.logger.exception("Lifecycle task failed task=%s", task_name)
            await self.notify_critical_error(error)


def restart_process() -> None:
    logger.warning("Restarting bot process")
    os.execv(sys.executable, [sys.executable] + sys.argv)
