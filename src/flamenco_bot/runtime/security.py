import logging
import time
from collections import OrderedDict, deque
from typing import Any, Awaitable, Callable, Deque, Tuple

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


logger = logging.getLogger("bot.security")
SecurityHandler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class SecurityMiddleware(BaseMiddleware):
    def __init__(
        self,
        max_events: int = 10,
        window_seconds: float = 10.0,
        max_tracked_users: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_events < 1 or window_seconds <= 0 or max_tracked_users < 1:
            raise ValueError(
                "Параметры ограничения запросов должны быть положительными"
            )
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.max_tracked_users = max_tracked_users
        self.clock = clock
        self._events: OrderedDict[int, Tuple[Deque[float], float, bool]] = OrderedDict()

    async def __call__(
        self,
        handler: SecurityHandler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender = getattr(event, "from_user", None)
        if sender is None:
            return await handler(event, data)

        chat = getattr(event, "chat", None)
        if chat is None:
            chat = getattr(getattr(event, "message", None), "chat", None)
        if chat is not None and getattr(chat, "type", None) != "private":
            logger.warning(
                "Rejected non-private event chat_type=%s event=%s telegram_id=%s",
                getattr(chat, "type", None),
                event.__class__.__name__,
                sender.id,
            )
            return None

        now = self.clock()
        self._remove_expired_users(now)
        bucket = self._events.get(sender.id)
        if bucket is None:
            while len(self._events) >= self.max_tracked_users:
                self._events.popitem(last=False)
            timestamps: Deque[float] = deque()
            warned = False
        else:
            timestamps, _, warned = bucket
            while timestamps and now - timestamps[0] >= self.window_seconds:
                timestamps.popleft()
            if not timestamps:
                warned = False

        if len(timestamps) >= self.max_events:
            if not warned:
                logger.warning(
                    "Rate limit exceeded telegram_id=%s event=%s",
                    sender.id,
                    event.__class__.__name__,
                )
            self._events[sender.id] = (timestamps, now, True)
            self._events.move_to_end(sender.id)
            return None

        timestamps.append(now)
        self._events[sender.id] = (timestamps, now, warned)
        self._events.move_to_end(sender.id)
        return await handler(event, data)

    def _remove_expired_users(self, now: float) -> None:
        while self._events:
            telegram_id, (_, last_seen, _) = next(iter(self._events.items()))
            if now - last_seen < self.window_seconds:
                break
            del self._events[telegram_id]
