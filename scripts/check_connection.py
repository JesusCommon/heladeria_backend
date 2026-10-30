import asyncio
import time
import structlog
from heladeria_backend.config.settings import settings
from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
    create_mongo_client,
    ping_mongo,
)
from heladeria_backend.shared.adapters.outbound.persistence.mongo.unit_of_work import (
    MongoUnitOfWork,
)

logger = structlog.get_logger()

_TRANSACTIONAL_TOPOLOGIES = {
    "ReplicaSetWithPrimary",
    "ReplicaSetNoPrimary",
    "Sharded",
    "LoadBalanced",
}


async def main() -> None:
    print("=" * 60)
    print(f"  Diagnóstico de conexión MongoDB")
    print("=" * 60)
    print(f"  Database: {settings.mongo.database}")
    print(f"  URL:      {settings.mongo.url.split('@')[-1]}")
    print(f"  Pool:     min={settings.mongo.pool_min_size} max={settings.mongo.pool_max_size}")
    print("=" * 60)

    client = create_mongo_client()

    try:
        start = time.perf_counter()
        await ping_mongo(client, timeout_ms=5000)
        latency_ms = (time.perf_counter() - start) * 1000
        print(f"  ✓ Ping exitoso ({latency_ms:.2f} ms)")

        topology = client.topology_description.topology_type_name
        print(f"  ✓ Topología: {topology}")

        server_info = await client.admin.command("ping")
        build_info = await client.admin.command("buildInfo")
        print(f"  ✓ MongoDB version: {build_info['version']}")

        uow = MongoUnitOfWork(client, settings.mongo.database)
        if uow._supports_transactions:
            print("  ✓ Transacciones: SOPORTADAS (replica set)")
        else:
            print("  ⚠ Transacciones: NO soportadas (standalone)")
            print("    → En producción (Atlas) estarán activas")

        db = client[settings.mongo.database]
        test_collection = db["_connection_probe"]
        await test_collection.insert_one({"probe": True, "ts": time.time()})
        count = await test_collection.count_documents({"probe": True})
        await test_collection.drop()
        print(f"  ✓ Escritura/lectura: OK ({count} doc)")

        print("=" * 60)
        print("  ✓ Conexión SALUDABLE")
        print("=" * 60)

    except Exception as e:
        print("=" * 60)
        print(f"  ✗ Error de conexión: {e}")
        print("=" * 60)
        raise
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())