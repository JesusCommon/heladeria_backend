"""Helper transaccional con reintentos de errores transitorios."""

import asyncio
import random
from typing import Any, Awaitable, Callable

import structlog
from pymongo.errors import OperationFailure, PyMongoError

from heladeria_backend.shared.adapters.outbound.persistence.mongo.unit_of_work import (
    MongoUnitOfWork,
)

logger = structlog.get_logger()

MAX_ATTEMPTS = 6


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, OperationFailure):
        labels = getattr(exc, "errorLabels", None) or []
        if "TransientTransactionError" in labels:
            return True
        if getattr(exc, "code", None) == 112:  # WriteConflict
            return True
    return False


async def run_transaction(
    uow_factory: Callable[[], MongoUnitOfWork],
    body: Callable[[Any], Awaitable[Any]],
) -> Any:
    """Ejecuta `body(session)` dentro de una transacción del UoW.

    - La sesión se obtiene EXPLÍCITAMENTE de uow.session y cada operación
      la propaga (regla de persistencia del proyecto).
    - TransientTransactionError/WriteConflict ⇒ nueva tx con backoff+random
      para des-sincronizar competidores (el loser debe re-leer estado fresco).
    """
    attempt = 0
    while True:
        attempt += 1
        unit = uow_factory() if callable(uow_factory) else uow_factory
        retryable = False
        try:
            async with unit as uow_ctx:
                session = uow_ctx.session
                try:
                    result = await body(session)
                    return result
                except OperationFailure as exc:
                    # marcar y RE-LANZAR: el __aexit__ verá la excepción y hará
                    # rollback (no commit sobre la tx abortada)
                    retryable = attempt < MAX_ATTEMPTS and _is_transient(exc)
                    raise
        except OperationFailure:
            if retryable:
                await asyncio.sleep(min(0.5, 0.05 * attempt + random.uniform(0.01, 0.08)))
                logger.warning("orders.transaction.transient_retry", attempt=attempt)
                continue
            raise
        except Exception:
            # el commit pertenece al __aexit__; un error aborta limpio
            raise
