"""Arranque del backend: conexión, índices, seed OWNER y tarea de expiración."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from heladeria_backend.bootstrap.container import build_container
from heladeria_backend.bootstrap.indexes import ensure_indexes
from heladeria_backend.config.settings import settings
from heladeria_backend.identity.application.use_cases import seed_owner_if_empty
from heladeria_backend.observability.logging import reconfigure_uvicorn_loggers
from heladeria_backend.orders.application.use_cases import expire_stale_orders
from heladeria_backend.shared.adapters.outbound.persistence.mongo import MongoConnection

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    reconfigure_uvicorn_loggers()
    logger.info("mongo.client.initializing", app_name=settings.app.slug)

    connection = MongoConnection()
    await connection.connect()

    app.state.mongo_connection = connection
    app.state.mongo_client = connection.client

    if connection.client is not None:
        app.state.container = build_container(connection.client)
        await ensure_indexes(connection.client, settings.mongo.database)
        if settings.admin_seed.enabled:
            await seed_owner_if_empty(
                app.state.container.identity,
                settings.admin_seed.owner_username,
                settings.admin_seed.owner_password,
            )
        expire_task = asyncio.create_task(_expiration_sweeper(app))
    else:
        expire_task = None

    try:
        yield
    finally:
        if expire_task is not None:
            expire_task.cancel()
        logger.info("mongo.client.closing")
        await connection.close()
        logger.info("mongo.client.closed")


async def _expiration_sweeper(app: FastAPI) -> None:
    """Libera reservas de pedidos aún PENDING vencidos (§ 3.6)."""
    while True:
        await asyncio.sleep(settings.business.expiration_sweep_seconds)
        container = getattr(app.state, "container", None)
        if container is None or not app.state.mongo_connection.connected:
            continue
        try:
            expired = await expire_stale_orders(container.orders_deps)
            if expired:
                logger.info("orders.expiration_swept", count=len(expired))
        except Exception:
            logger.exception("orders.expiration_sweep.failed")
