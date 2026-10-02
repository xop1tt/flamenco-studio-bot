"""FastAPI-приложение сайта.

Второй интерфейс к той же системе, что и Telegram-бот: тот же PostgreSQL,
те же сервисы (``..services``). Бот и сайт не держат отдельных копий
бизнес-логики — см. ``CLAUDE.md``, принцип "один backend, одна БД".
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from aiogram import Bot
from fastapi import FastAPI

from ..database import InMemoryRepository, PostgresRepository, is_database_configured
from ..payments import YooKassaClient
from ..runtime.security import SupportRateLimiter
from ..services import AuthService
from .config import WebConfig
from .routers.auth import router as auth_router
from .routers.bookings import router as bookings_router
from .routers.packages import router as packages_router
from .routers.payments import router as payments_router
from .routers.schedule import router as schedule_router
from .routers.support import router as support_router
from .routers.users import router as users_router


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

    # Тот же бот, что и в main.py: нужен только чтобы рассылать уведомления
    # администраторам (AdminNotifier), не для приёма обновлений/polling.
    bot = Bot(token=WebConfig.BOT_TOKEN)

    # Тот же shop_id/secret_key, что у бота (один магазин ЮKassa), но
    # отдельный return_url — оплата, начатая на сайте, должна вернуть
    # пользователя на сайт, а не в Telegram-чат бота. Пока
    # WEB_YOOKASSA_RETURN_URL не задан, YooKassaClient.is_configured — False
    # и checkout на сайте недоступен (503), что ожидаемо на этом этапе.
    payment_gateway = YooKassaClient(
        WebConfig.YOOKASSA_SHOP_ID,
        WebConfig.YOOKASSA_SECRET_KEY,
        WebConfig.WEB_YOOKASSA_RETURN_URL,
    )

    app.state.repository = repository
    app.state.auth_service = AuthService(repository, WebConfig.BOT_TOKEN)
    app.state.session_secret_key = WebConfig.SESSION_SECRET_KEY
    app.state.bot = bot
    app.state.support_limiter = SupportRateLimiter()
    app.state.payment_gateway = payment_gateway
    try:
        yield
    finally:
        await bot.session.close()
        await repository.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Flamenco Studio API", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(schedule_router)
    app.include_router(packages_router)
    app.include_router(bookings_router)
    app.include_router(support_router)
    app.include_router(users_router)
    app.include_router(payments_router)

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
