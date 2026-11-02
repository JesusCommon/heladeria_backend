import pytest_asyncio

from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    create_mongo_client,
)
from tests.integration.helpers import (  # noqa: F401
    container,
    test_client,
    test_db,
)

TEST_DATABASE = "heladeria_test_db"

@pytest_asyncio.fixture
async def mongo_client():
    client = create_mongo_client()
    yield client
    await client.close()

@pytest_asyncio.fixture
async def mongo_db(mongo_client):
    db = mongo_client[TEST_DATABASE]
    yield db
    for name in await db.list_collection_names():
        await db.drop_collection(name)
