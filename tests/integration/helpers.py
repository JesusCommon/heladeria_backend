"""Infraestructura de pruebas de integración (Mongo real con replica set)."""

import uuid

import pytest_asyncio

from heladeria_backend.bootstrap.container import build_container
from heladeria_backend.bootstrap.indexes import ensure_indexes
from heladeria_backend.shared.adapters.outbound.persistence.mongo.client import (
    create_mongo_client,
)
from heladeria_backend.shared.adapters.outbound.persistence.mongo.connection import (
    MongoConnection,
)

URI = "mongodb://localhost:27018/?replicaSet=rs0"


@pytest_asyncio.fixture
async def test_client():
    client = create_mongo_client()
    yield client
    await client.close()


def db_name() -> str:
    return f"heladeria_it_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_db(test_client):
    name = db_name()
    db = test_client[name]
    yield test_client, name, db
    await test_client.drop_database(name)


@pytest_asyncio.fixture
async def container(test_db):
    client, name, _db = test_db
    await ensure_indexes(client, name)
    return build_container(client, database_name=name)
