import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    ping_mongo,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/health", tags=["health"])

_PING_TIMEOUT_MS = 2000

@router.get("/live")
async def liveness():
    return {"status": "ok"}

@router.get("/ready")
async def readiness(request: Request):
    client = await _get_connected_client(request)

    if client is None:
        logger.warning("readiness.client.missing")
        return _database_unavailable()

    try:
        await ping_mongo(client, timeout_ms=_PING_TIMEOUT_MS)
        return {"status": "ok", "database": "connected"}
    except Exception:
        logger.exception("readiness.ping.failed")
        return _database_unavailable()

@router.get("/status")
async def status(request: Request):
    result = {
        "app": {"status": "running"},
        "database": {"status": "disconnected"},
    }

    client = getattr(request.app.state, "mongo_client", None)
    connection = getattr(request.app.state, "mongo_connection", None)

    if connection is not None and await connection.ensure_connected():
        client = connection.client

    if client is None:
        return result

    try:
        await ping_mongo(client, timeout_ms=_PING_TIMEOUT_MS)
        result["database"]["status"] = "connected"
    except Exception:
        logger.exception("status.ping.failed")
        result["database"]["status"] = "unhealthy"

    return result


async def _get_connected_client(request: Request):
    """Devuelve un cliente vivo, reintentando la conexión si se degradó."""
    connection = getattr(request.app.state, "mongo_connection", None)

    if connection is not None:
        if await connection.ensure_connected():
            return connection.client
        return None

    # Fallback para estados construidos a mano (tests, scripts).
    return getattr(request.app.state, "mongo_client", None)


def _database_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"status": "error", "reason": "database_unavailable"},
    )
