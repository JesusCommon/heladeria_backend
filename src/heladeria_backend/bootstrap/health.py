import asyncio
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger()
router = APIRouter(prefix="/health", tags=["health"])

@router.get("/live")
async def liveness():
    return {"status": "ok"}

@router.get("/ready")
async def readiness(request: Request):
    client = getattr(request.app.state, "mongo_client", None)

    if client is None:
        logger.warning("readiness.client.missing")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "reason": "database_unavailable"},
        )

    try:
        await asyncio.wait_for(
            client.admin.command("ping"),
            timeout=2.0,
        )
        return {"status": "ok"}
    except Exception:
        logger.exception("readiness.ping.failed")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "reason": "database_unavailable"},
        )

@router.get("/status")
async def status(request: Request):
    client = getattr(request.app.state, "mongo_client", None)

    result = {
        "app": {"status": "running"},
        "database": {"status": "disconnected"},
    }

    if client is None:
        return result

    try:
        await asyncio.wait_for(
            client.admin.command("ping"),
            timeout=2.0,
        )
        result["database"]["status"] = "connected"
    except Exception:
        logger.exception("status.ping.failed")
        result["database"]["status"] = "unhealthy"

    return result