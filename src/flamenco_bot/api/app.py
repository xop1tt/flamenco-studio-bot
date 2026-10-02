"""FastAPI-приложение сайта.

Второй интерфейс к той же системе, что и Telegram-бот: тот же PostgreSQL,
те же сервисы (``..services``). Бот и сайт не держат отдельных копий
бизнес-логики — см. ``CLAUDE.md``, принцип "один backend, одна БД".
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from ..database import InMemoryRepository, PostgresRepository, is_database_configured
from ..services import AuthService
from .config import WebConfig
from .routers.auth import router as auth_router


logger = logging.getLogger("bot.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if WebConfig.ENV == "production" and not is_database_configured(
        WebConfig.DATABASE_URL
    ):
        raise RuntimeError(
            "DATABASE_URL must point to PostgreSQL in production; "
            "refusing to use temporary in-memory storage"
        )

    if is_database_configured(WebConfig.DATABASE_URL):
        repository = await PostgresRepository.connect(
            WebConfig.DATABASE_URL,
            ssl_ca_path=WebConfig.DATABASE_SSL_CA,
            pool_min_size=WebConfig.DATABASE_POOL_MIN_SIZE,
            pool_max_size=WebConfig.DATABASE_POOL_MAX_SIZE,
            ssl_mode=WebConfig.DATABASE_SSL_MODE,
            allow_insecure_local=WebConfig.ENV == "development",
        )
        logger.info("API storage backend=postgres")
    else:
        logger.warning("PostgreSQL is not configured; web accounts will be temporary")
        repository = InMemoryRepository()
    await repository.initialize()

    app.state.repository = repository
    app.state.auth_service = AuthService(repository, WebConfig.BOT_TOKEN)
    app.state.session_secret_key = WebConfig.SESSION_SECRET_KEY
    try:
        yield
    finally:
        await repository.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Flamenco Studio API", lifespan=lifespan)
    app.include_router(auth_router)

    @app.get("/api/health")
    async def health() -> dict:
        health_status = await app.state.repository.health_check()
        return {
            "backend": health_status.backend,
            "pool_size": health_status.pool_size,
            "idle_connections": health_status.idle_connections,
        }

    return app


app = create_app()
