import asyncio
import time

import structlog
from beanie import init_beanie
from pymongo import AsyncMongoClient

from heladeria_backend.config.settings import settings

from .client import create_mongo_client
from .health import ping_mongo

logger = structlog.get_logger()

_MAX_BACKOFF_SECONDS = 5.0
_MIN_RECONNECT_THROTTLE_MS = 2_000

class MongoConnection:
    """Gestiona el ciclo de vida de la conexión a MongoDB.

    Reintentar con backoff exponencial al arrancar y permitir reconexión
    perezosa desde los health checks si la conexión se degradó,
    de modo que la app se recupere sola cuando Mongo vuelva a estar
    disponible (sin necesidad de reiniciar el proceso).
    """

    def __init__(self, document_models: list | None = None) -> None:
        self._document_models = document_models or []
        self._client: AsyncMongoClient | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._next_attempt_at = 0.0

    @property
    def client(self) -> AsyncMongoClient | None:
        return self._client

    @property
    def connected(self) -> bool:
        return self._client is not None and self._initialized

    async def connect(self) -> None:
        """Intenta conectar con reintentos y backoff exponencial.

        Nunca lanza: si se agotan los intentos, la conexión queda en
        estado degradado y los health checks pueden reintentarla luego.
        """
        max_attempts = settings.mongo.connect_max_attempts

        for attempt in range(1, max_attempts + 1):
            try:
                await self._establish_connection()
                return
            except Exception:
                logger.warning(
                    "mongo.connect.attempt.failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    database=settings.mongo.database,
                )
                await self._discard_client()
                if attempt < max_attempts:
                    await self._wait_backoff(attempt)

        logger.error(
            "mongo.connect.exhausted",
            max_attempts=max_attempts,
            database=settings.mongo.database,
        )
        self._schedule_reconnect()

    async def ensure_connected(self) -> bool:
        """Se reconecta en frío si corresponda. Devuelve True si hay conexión.

        Con un pequeño throttle para que los health checks no generen
        intentos de reconexión constantes mientras Mongo está caído.
        """
        if self.connected:
            return True

        async with self._lock:
            if self.connected:
                return True
            if time.monotonic() < self._next_attempt_at:
                return False

            try:
                await self._establish_connection()
                return True
            except Exception:
                logger.warning(
                    "mongo.reconnect.failed",
                    database=settings.mongo.database,
                )
                await self._discard_client()
                self._schedule_reconnect()
                return False

    async def close(self) -> None:
        await self._discard_client()
        self._next_attempt_at = 0.0

    async def _establish_connection(self) -> None:
        client = create_mongo_client()

        try:
            await ping_mongo(
                client,
                timeout_ms=settings.mongo.server_selection_timeout_ms,
            )
            await init_beanie(
                database=client[settings.mongo.database],
                document_models=self._document_models,
            )
        except Exception:
            await self._safe_close(client)
            raise

        self._client = client
        self._initialized = True
        self._next_attempt_at = 0.0

        logger.info(
            "mongo.client.connected",
            app_name=settings.app.slug,
            database=settings.mongo.database,
        )

    async def _discard_client(self) -> None:
        client, self._client, self._initialized = self._client, None, False
        await self._safe_close(client)

    async def _safe_close(self, client: AsyncMongoClient | None) -> None:
        if client is None:
            return
        try:
            await client.close()
        except Exception:
            logger.exception("mongo.client.close.failed")

    def _schedule_reconnect(self) -> None:
        throttle_ms = max(_MIN_RECONNECT_THROTTLE_MS, settings.mongo.connect_backoff_ms * 2)
        self._next_attempt_at = time.monotonic() + throttle_ms / 1000

    async def _wait_backoff(self, attempt: int) -> None:
        delay = (settings.mongo.connect_backoff_ms / 1000) * (2 ** (attempt - 1))
        await asyncio.sleep(min(_MAX_BACKOFF_SECONDS, delay))
