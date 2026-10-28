from fastapi import FastAPI
from heladeria_backend.bootstrap.health import router as health_router
from heladeria_backend.bootstrap.lifespan import lifespan
from heladeria_backend.config.settings import settings
from heladeria_backend.observability.logging import setup_logging
from heladeria_backend.shared.adapters.inbound.http.middleware import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
)

def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
    app.include_router(health_router)

    @app.get("/")
    async def root():
        return {
            "app": settings.app.name,
            "version": settings.app.version,
            "environment": settings.app.environment,
        }

    return app