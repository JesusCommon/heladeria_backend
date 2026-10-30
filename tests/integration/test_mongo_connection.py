import pytest
from heladeria_backend.config.settings import get_settings
from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    create_mongo_client,
    ping_mongo,
)

pytestmark = pytest.mark.integration

async def test_ping_succeeds(mongo_client):
    await ping_mongo(mongo_client, timeout_ms=2000)

async def test_client_pool_options_applied():
    settings = get_settings()
    client = create_mongo_client()
    await ping_mongo(client)

    assert client.options.pool_options.max_pool_size == settings.mongo.pool_max_size
    assert client.options.pool_options.min_pool_size == settings.mongo.pool_min_size
    await client.close()

async def test_client_timeouts_configured():
    settings = get_settings()
    client = create_mongo_client()
    await ping_mongo(client)

    assert client.options.server_selection_timeout == (
        settings.mongo.server_selection_timeout_ms / 1000
    )

    assert client is not None
    await client.close()

async def test_client_closes_cleanly():
    client = create_mongo_client()
    await ping_mongo(client)
    await client.close()
    await client.close()

async def test_topology_detection(mongo_client):
    await ping_mongo(mongo_client)

    topology = mongo_client.topology_description.topology_type_name
    assert topology in (
        "Single",
        "ReplicaSetWithPrimary",
        "ReplicaSetNoPrimary",
        "Sharded",
        "LoadBalanced",
    )