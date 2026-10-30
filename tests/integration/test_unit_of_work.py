import pytest
from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    MongoUnitOfWork,
)

pytestmark = pytest.mark.integration

async def test_uow_context_manager(mongo_client, mongo_db):
    async with MongoUnitOfWork(mongo_client, mongo_db.name) as uow:
        await uow.database["_test_uow"].insert_one({"value": 1})
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