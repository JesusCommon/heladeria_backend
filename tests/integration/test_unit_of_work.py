import pytest

from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    MongoUnitOfWork,
)

pytestmark = pytest.mark.integration

async def test_uow_context_manager(mongo_client, mongo_db):
    async with MongoUnitOfWork(mongo_client, mongo_db.name) as uow:
        # Nota de diseño: dentro del UoW toda operación debe recibir
        # explícitamente la sesión; es lo que harán los repositorios del dominio.
        await uow.database["_test_uow"].insert_one(
            {"value": 1}, session=uow.session
        )
        await uow.commit()

    count = await mongo_db["_test_uow"].count_documents({"value": 1})
    assert count == 1

async def test_uow_detects_transaction_support(mongo_client):
    uow = MongoUnitOfWork(mongo_client, "test_db")
    assert isinstance(uow._supports_transactions, bool)

async def test_uow_commit_without_transaction_is_safe(mongo_client):
    async with MongoUnitOfWork(mongo_client, "test_db") as uow:
        if not uow._supports_transactions:
            await uow.commit()
            await uow.commit()

async def test_uow_session_closed_after_exit(mongo_client):
    async with MongoUnitOfWork(mongo_client, "test_db") as uow:
        session = uow.session
        assert session is not None

    assert uow.session is None

async def test_uow_transaction_active_inside_context(mongo_client, mongo_db):
    uow = MongoUnitOfWork(mongo_client, mongo_db.name)
    if not uow._supports_transactions:
        pytest.skip("topología sin transacciones")

    async with uow:
        assert uow._transaction_active is True
        await uow.database["_test_uow"].insert_one(
            {"value": 1}, session=uow.session
        )

    # Al salir sin excepción se hace commit automáticamente: los datos quedan visibles.
    count = await mongo_db["_test_uow"].count_documents({"value": 1})
    assert count == 1

async def test_uow_rollback_discards_changes_on_error(mongo_client, mongo_db):
    uow = MongoUnitOfWork(mongo_client, mongo_db.name)
    if not uow._supports_transactions:
        pytest.skip("topología sin transacciones")

    with pytest.raises(RuntimeError):
        async with uow:
            # La operación se ejecuta dentro de la transacción (con session).
            await uow.database["_test_uow"].insert_one(
                {"value": 1}, session=uow.session
            )
            raise RuntimeError("error simulado tras insertar")

    # El rollback abortó la transacción: el insert fue descartado.
    count = await mongo_db["_test_uow"].count_documents({"value": 1})
    assert count == 0

async def test_uow_insert_without_session_escapes_transaction(mongo_client, mongo_db):
    """Sentinela del peligro detectado: una operación SIN session no forma parte
    de la transacción y persiste aunque la sesión haga rollback.

    Los repositorios de la Fase 3 deben pasar siempre la sesión para no violar
    la consistencia transaccional del dominio.
    """
    uow = MongoUnitOfWork(mongo_client, mongo_db.name)
    if not uow._supports_transactions:
        pytest.skip("topología sin transacciones")

    with pytest.raises(RuntimeError):
        async with uow:
            await uow.database["_test_uow"].insert_one({"value": 1})
            raise RuntimeError("error simulado; el insert no estaba en la tx")

    # Contraste con test_uow_rollback_discards_changes_on_error: sin session,
    # la escritura quedó fuera de la transacción.
    count = await mongo_db["_test_uow"].count_documents({"value": 1})
    assert count == 1
