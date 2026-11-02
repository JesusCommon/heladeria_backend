"""Creación de índices críticos (idempotente al arrancar)."""

from pymongo import AsyncMongoClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

import structlog

logger = structlog.get_logger()


async def ensure_indexes(client: AsyncMongoClient, database_name: str) -> None:
    db = client[database_name]
    try:
        # catálogo
        await db["products"].create_index([("name", ASCENDING)])
        await db["catalog_items"].create_index([("name", ASCENDING), ("kind", ASCENDING)], background=True)

        # inventario
        await db["inventory_items"].create_index([("name", ASCENDING)], background=True)
        await db["inventory_movements"].create_index("inventory_item_id", background=True)
        await db["inventory_movements"].create_index([("inventory_item_id", ASCENDING), ("occurred_at", DESCENDING)], background=True)
        await db["reservations"].create_index([("order_id", ASCENDING)], background=True)
        await db["reservations"].create_index([("status", ASCENDING), ("expires_at", ASCENDING)], background=True)

        # tables
        await db["tables"].create_index([("number", ASCENDING)], unique=True, background=True)
        await db["devices"].create_index(
            [("token_hash", ASCENDING)], unique=True, background=True, sparse=True
        )
        await db["devices"].create_index([("link_code", ASCENDING)], background=True, sparse=True)
        await db["table_sessions"].create_index("table_id", background=True)
        # P1: una sesión abierta por mesa
        await db["table_sessions"].create_index(
            [("table_id", ASCENDING), ("status", ASCENDING)],
            unique=True,
            background=True,
            partialFilterExpression={"status": "open"},
        )
        await db["customer_sessions"].create_index(
            "token_hash", unique=True, background=True, sparse=True
        )

        # orders + idempotencia D4 (índice único en (key, customer_session_id))
        await db["orders"].create_index([("order_number", ASCENDING)], unique=True, background=True)
        await db["orders"].create_index([("idempotency_key", ASCENDING), ("customer_session_id", ASCENDING)], background=True)
        await db["orders"].create_index([("status", ASCENDING), ("table_id", ASCENDING)], background=True)
        await db["idempotency_keys"].create_index(
            [("key", ASCENDING), ("customer_session_id", ASCENDING)], unique=True, background=True
        )
        await db["idempotency_keys"].create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            background=True,
        )

        # identidad
        await db["admin_users"].create_index([("username", ASCENDING)], unique=True, background=True)
        logger.info("bootstrap.indexes.ok")
    except OperationFailure as e:
        # Mongo standalone sin replica set no permite create_index con session, etc.
        logger.warning("bootstrap.indexes.warn", error=str(e))
