from contextlib import asynccontextmanager
from typing import AsyncGenerator
import structlog
from beanie import init_beanie
from fastapi import FastAPI
from heladeria_backend.config.settings import settings
from heladeria_backend.observability.logging import reconfigure_uvicorn_loggers
from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    create_mongo_client,
    ping_mongo,
)

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    reconfigure_uvicorn_loggers()

    client = None

    try:
        logger.info(
            "mongo.client.initializing",
            app_name=settings.app.slug,
            database=settings.mongo.database,
            pool_min=settings.mongo.pool_min_size,
            pool_max=settings.mongo.pool_max_size,
        )

        client = create_mongo_client()
        await ping_mongo(
            client,
            timeout_ms=settings.mongo.server_selection_timeout_ms,
        )

        await init_beanie(
            database=client[settings.mongo.database],
            document_models=[],
        )

        app.state.mongo_client = client
        logger.info("mongo.client.connected")

    except Exception:
        logger.exception(
            "mongo.client.failed",
            database=settings.mongo.database,
        )
        if client is not None:
            try:
                await client.close()
            except Exception:
                logger.exception("mongo.client.close.failed")
        app.state.mongo_client = None
        client = None

    yield

    if client is not None:
        try:
            logger.info("mongo.client.closing")
            await client.close()
            logger.info("mongo.client.closed")
        except Exception:
            logger.exception("mongo.client.close.failed")