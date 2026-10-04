"""Логи веб-API: логгеры ``bot.*`` (сервисы, репозиторий, сверка платежей)
в stderr процесса — их показывает ``docker compose logs api``.

Без этой настройки в процессе API были видны только WARNING+ без времени и
источника: INFO (например, сверка платежей) терялся. Запись идёт через
``QueueHandler``/``QueueListener``: event loop только кладёт запись в
очередь, в поток вывода пишет отдельный поток. Содержимое сообщений — те же
обезличенные сообщения, что и в боте (telegram_id, id сущностей), без
паролей, токенов сессий, Telegram-payload и платёжных секретов.
"""

import atexit
import logging
import logging.handlers
import queue
import sys
from typing import Optional

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_listener: Optional[logging.handlers.QueueListener] = None


def _stop_listener() -> None:
    """Дописать очередь при выходе процесса (повторный вызов безопасен)."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def configure_api_logging(level: int = logging.INFO) -> None:
    """Идемпотентно: повторный вызов (перезапуск lifespan) ничего не меняет."""
    global _listener
    if _listener is not None:
        return
    output = logging.StreamHandler(sys.stderr)
    output.setFormatter(logging.Formatter(LOG_FORMAT))
    records: queue.Queue = queue.Queue(-1)
    _listener = logging.handlers.QueueListener(
        records, output, respect_handler_level=True
    )
    _listener.start()
    atexit.register(_stop_listener)

    logger = logging.getLogger("bot")
    logger.addHandler(logging.handlers.QueueHandler(records))
    logger.setLevel(level)
    # Не дублировать записи через корневой логгер (uvicorn/по умолчанию).
    logger.propagate = False
