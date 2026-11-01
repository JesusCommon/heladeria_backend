from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from heladeria_backend.config.settings import settings
from heladeria_backend.observability.logging import reconfigure_uvicorn_loggers
from heladeria_backend.shared.adapters.outbound.persistence.mongo import MongoConnection

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    reconfigure_uvicorn_loggers()

    logger.info(
        "mongo.client.initializing",
        app_name=settings.app.slug,
        database=settings.mongo.database,
        pool_min=settings.mongo.pool_min_size,
        pool_max=settings.mongo.pool_max_size,
    )

    connection = MongoConnection()
    # Devuelve con reintentos y en el peor caso queda degradada
    # (readiness en 503) sin tumbar el servidor; los health checks
    # vuelven a intentar la reconexión de forma perezosa.
    await connection.connect()

    app.state.mongo_connection = connection
    app.state.mongo_client = connection.client

    yield

    logger.info("mongo.client.closing")
    await connection.close()
    logger.info("mongo.client.closed")
