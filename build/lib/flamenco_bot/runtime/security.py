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
        max_global_events: int = 100,
        global_window_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            max_events < 1
            or window_seconds <= 0
            or max_tracked_users < 1
            or max_global_events < 1
            or global_window_seconds <= 0
        ):
            raise ValueError(
                "Параметры ограничения запросов должны быть положительными"
            )
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.max_tracked_users = max_tracked_users
        self.max_global_events = max_global_events
        self.global_window_seconds = global_window_seconds
        self.clock = clock
        self._events: OrderedDict[int, Tuple[Deque[float], float, bool]] = OrderedDict()
        self._global_events: Deque[float] = deque()
        self._global_warned = False

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
        while (
            self._global_events
            and now - self._global_events[0] >= self.global_window_seconds
        ):
            self._global_events.popleft()
        if not self._global_events:
            self._global_warned = False
        if len(self._global_events) >= self.max_global_events:
            if not self._global_warned:
                logger.warning(
                    "Global rate limit exceeded event=%s",
                    event.__class__.__name__,
                )
                self._global_warned = True
            return None
        self._global_events.append(now)

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


class AuthRateLimiter:
    """Ограничение попыток входа/регистрации на ``/api/auth/*`` по IP.

    До появления этого класса эндпоинты веб-аутентификации не имели защиты
    от перебора пароля или подписи Telegram (см. аудит безопасности).
    Ключ — IP клиента, а не email/telegram_id из тела запроса: иначе
    атакующий просто перебирал бы разные учётные записи без ограничений.
    """

    def __init__(
        self,
        max_attempts: int = 10,
        window_seconds: float = 300.0,
        max_tracked_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1 or window_seconds <= 0 or max_tracked_keys < 1:
            raise ValueError(
                "Параметры ограничения попыток входа должны быть положительными"
            )
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self.clock = clock
        self._events: OrderedDict[str, Deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = self.clock()
        while self._events:
            oldest_key, oldest_events = next(iter(self._events.items()))
            while oldest_events and now - oldest_events[0] >= self.window_seconds:
                oldest_events.popleft()
            if oldest_events:
                break
            del self._events[oldest_key]
        events = self._events.get(key)
        if events is None:
            while len(self._events) >= self.max_tracked_keys:
                self._events.popitem(last=False)
            events = deque()
            self._events[key] = events
        else:
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.max_attempts:
                self._events.move_to_end(key)
                return False
        events.append(now)
        self._events.move_to_end(key)
        return True


class SupportRateLimiter:
    def __init__(
        self,
        max_messages: int = 5,
        window_seconds: float = 300.0,
        max_tracked_users: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_messages < 1 or window_seconds <= 0 or max_tracked_users < 1:
            raise ValueError(
                "Параметры ограничения обращений должны быть положительными"
            )
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.max_tracked_users = max_tracked_users
        self.clock = clock
        self._events: OrderedDict[int, Deque[float]] = OrderedDict()

    def allow(self, telegram_id: int) -> bool:
        now = self.clock()
        while self._events:
            oldest_user_id, oldest_events = next(iter(self._events.items()))
            while oldest_events and now - oldest_events[0] >= self.window_seconds:
                oldest_events.popleft()
            if oldest_events:
                break
            del self._events[oldest_user_id]
        events = self._events.get(telegram_id)
        if events is None:
            while len(self._events) >= self.max_tracked_users:
                self._events.popitem(last=False)
            events = deque()
            self._events[telegram_id] = events
        else:
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.max_messages:
                self._events.move_to_end(telegram_id)
                return False
        events.append(now)
        self._events.move_to_end(telegram_id)
        return True
