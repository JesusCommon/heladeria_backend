import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import structlog
from fastapi import FastAPI
from pymongo import AsyncMongoClient
from heladeria_backend.config.settings import settings
from heladeria_backend.observability.logging import reconfigure_uvicorn_loggers

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    reconfigure_uvicorn_loggers()
    client: AsyncMongoClient | None = None

    try:
        logger.info(
            "mongo.client.initializing",
            database=settings.mongo.database,
            app_name=settings.app.slug,
            pool_min=settings.mongo.pool_min_size,
            pool_max=settings.mongo.pool_max_size,
        )

        client = AsyncMongoClient(
            settings.mongo.url,
            appName=settings.app.slug,
            minPoolSize=settings.mongo.pool_min_size,
            maxPoolSize=settings.mongo.pool_max_size,
            serverSelectionTimeoutMS=settings.mongo.server_selection_timeout_ms,
            connectTimeoutMS=settings.mongo.connect_timeout_ms,
            socketTimeoutMS=settings.mongo.socket_timeout_ms,
            waitQueueTimeoutMS=settings.mongo.wait_queue_timeout_ms,
            retryWrites=True,
            retryReads=True,
        )

        await asyncio.wait_for(
            client.admin.command("ping"),
            timeout=settings.mongo.server_selection_timeout_ms / 1000,
        )

        app.state.mongo_client = client
        logger.info("mongo.client.connected")

    except Exception:
        logger.exception(
            "mongo.client.connection.failed",
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