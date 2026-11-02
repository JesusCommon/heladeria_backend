from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from heladeria_backend.bootstrap.health import router as health_router
from heladeria_backend.bootstrap.lifespan import lifespan
from heladeria_backend.catalog.adapters.api import router as catalog_admin_router
from heladeria_backend.catalog.adapters.public_api import router as public_catalog_router
from heladeria_backend.config.settings import settings
from heladeria_backend.identity.adapters.api import router as identity_router
from heladeria_backend.inventory.adapters.api import router as inventory_router
from heladeria_backend.observability.logging import setup_logging
from heladeria_backend.orders.adapters.api import admin_router as orders_admin_router
from heladeria_backend.orders.adapters.api import router as orders_router
from heladeria_backend.shared.adapters.inbound.http.middleware import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
)
from heladeria_backend.shared.domain.errors import DomainError
from heladeria_backend.tables.adapters.api import public_router as tables_public_router
from heladeria_backend.tables.adapters.api import router as tables_admin_router

API_V1 = "/api/v1"


def error_payload(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
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

    # el dominio habla con HTTP solo por este mapeo de errores
    app.add_exception_handler(DomainError, error_payload)

    app.include_router(health_router)
    app.include_router(identity_router, prefix=API_V1)
    app.include_router(catalog_admin_router, prefix=API_V1)
    app.include_router(public_catalog_router, prefix=API_V1)
    app.include_router(inventory_router, prefix=API_V1)
    app.include_router(tables_admin_router, prefix=API_V1)
    app.include_router(tables_public_router, prefix=API_V1)
    app.include_router(orders_router, prefix=API_V1)
    app.include_router(orders_admin_router, prefix=API_V1)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', str(e))}"
                    for e in exc.errors()
                ],
                "code": "validation_error",
            },
        )

    @app.get("/")
    async def root():
        return {
            "app": settings.app.name,
            "version": settings.app.version,
            "environment": settings.app.environment,
        }

    return app
