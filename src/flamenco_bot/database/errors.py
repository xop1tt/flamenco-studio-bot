"""Распознавание ошибок "PostgreSQL недоступна" для бота и веб-API.

Оба интерфейса показывают пользователю одно и то же: сервис временно
недоступен — вместо 500/молчания. Сюда относятся только сбои соединения и
перегрузка сервера БД; ошибки самих запросов (нарушение ограничений,
синтаксис) — это баги, а не недоступность, и обрабатываются как раньше.
"""

import asyncio
import errno
import socket

import asyncpg

from .repository import DatabaseUnavailableError


DATABASE_UNAVAILABLE_ERRORS = (
    DatabaseUnavailableError,
    # Соединение не установлено/потеряно посреди запроса.
    asyncpg.PostgresConnectionError,
    # Сервер стартует, останавливается или упал.
    asyncpg.CannotConnectNowError,
    asyncpg.AdminShutdownError,
    asyncpg.CrashShutdownError,
    asyncpg.TooManyConnectionsError,
    # Таймаут подключения или command_timeout пула.
    asyncio.TimeoutError,
    TimeoutError,
    # ConnectionRefusedError/ConnectionResetError, DNS.
    ConnectionError,
    socket.gaierror,
)

_UNAVAILABLE_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.ETIMEDOUT,
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
}


def is_database_unavailable(error: BaseException) -> bool:
    if isinstance(error, DATABASE_UNAVAILABLE_ERRORS):
        return True
    return isinstance(error, OSError) and error.errno in _UNAVAILABLE_ERRNOS
