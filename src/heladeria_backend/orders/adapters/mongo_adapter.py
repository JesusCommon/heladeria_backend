"""Repositorios Mongo de Orders + generador de número de pedido."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from heladeria_backend.orders.domain.order import (
    IdempotencyRecord,
    Order,
    OrderStatus,
)
from heladeria_backend.orders.domain.ports import (
    IdempotencyRepository,
    OrderNumberPort,
    OrderRepository,
)
from heladeria_backend.shared.adapters.outbound.persistence.mongo.repo_mixins import (
    dump_bson,
    load,
)
from heladeria_backend.shared.domain.errors import ConflictError


def _now() -> datetime:
    return datetime.now(UTC)


class MongoOrderRepository(OrderRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, order: Order, session: Any | None = None) -> Order:
        order.updated_at = _now()
        doc = dump_bson(order)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        try:
            await self._db["orders"].replace_one(
                {"_id": order.id}, doc, upsert=True, session=session
            )
        except DuplicateKeyError:
            raise ConflictError("Duplicado en orders (idempotencia ya tomada)")
        return order

    async def get(self, order_id: str, session: Any | None = None) -> Order | None:
        doc = await self._db["orders"].find_one({"_id": order_id}, session=session)
        return load(Order, doc) if doc else None

    async def get_by_idempotency_key(
        self, key: str, customer_session_id: str, session: Any | None = None
    ) -> Order | None:
        doc = await self._db["orders"].find_one(
            {"idempotency_key": key, "customer_session_id": customer_session_id},
            session=session,
        )
        return load(Order, doc) if doc else None

    async def list(
        self,
        status: OrderStatus | None = None,
        table_id: str | None = None,
        customer_session_id: str | None = None,
        session: Any | None = None,
    ) -> list[Order]:
        q: dict[str, Any] = {}
        if status:
            q["status"] = status.value
        if table_id:
            q["table_id"] = table_id
        if customer_session_id:
            q["customer_session_id"] = customer_session_id
        docs = (
            await self._db["orders"].find(q, session=session)
            .sort("order_number", -1).to_list(500)
        )
        return [load(Order, d) for d in docs]

    async def list_pending_created_before(
        self, cutoff: datetime, session: Any | None = None
    ) -> list[Order]:
        docs = (
            await self._db["orders"]
            .find({"status": "pending", "created_at": {"$lt": cutoff}}, session=session)
            .to_list(500)
        )
        return [load(Order, d) for d in docs]


class MongoIdempotencyRepository(IdempotencyRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def insert(self, record: IdempotencyRecord, session: Any) -> None:
        doc = dump_bson(record)
        # la clave única es (key, customer_session_id)
        await self._db["idempotency_keys"].insert_one(doc, session=session)

    async def find(
        self, key: str, customer_session_id: str, session: Any | None = None
    ) -> IdempotencyRecord | None:
        doc = await self._db["idempotency_keys"].find_one(
            {"key": key, "customer_session_id": customer_session_id},
            session=session,
        )
        return load(IdempotencyRecord, doc) if doc else None

    async def renew(
        self, key: str, customer_session_id: str, expires_at: datetime, session: Any
    ) -> None:
        await self._db["idempotency_keys"].replace_one(
            {"key": key, "customer_session_id": customer_session_id},
            {
                "key": key,
                "customer_session_id": customer_session_id,
                "order_id": None,
                "created_at": datetime.now(UTC),
                "expires_at": expires_at,
            },
            session=session,
        )


    async def update_order_id(
        self, key: str, customer_session_id: str, order_id: str, session: Any
    ) -> None:
        await self._db["idempotency_keys"].update_one(
            {"key": key, "customer_session_id": customer_session_id},
            {"$set": {"order_id": order_id}},
            session=session,
        )


class MongoOrderNumberPort(OrderNumberPort):
    """Contador atómico con findOneAndUpdate dentro de la misma tx."""

    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def next_number(self, session: Any) -> int:
        doc = await self._db["counters"].find_one_and_update(
            {"_id": "order_number"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
            session=session,
        )
        return int(doc["seq"])
