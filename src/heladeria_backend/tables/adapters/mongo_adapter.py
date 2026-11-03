"""Repositorios Mongo del módulo Tables."""

from datetime import UTC, datetime
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from heladeria_backend.shared.adapters.outbound.persistence.mongo.repo_mixins import (
    dump_bson,
    load,
)
from heladeria_backend.shared.domain.errors import ConflictError
from heladeria_backend.tables.domain.ports import (
    CustomerSessionRepository,
    DeviceRepository,
    TableRepository,
    TableSessionRepository,
)
from heladeria_backend.tables.domain.tables import (
    CustomerSession,
    Device,
    Table,
    TableSession,
)


def _now():
    return datetime.now(UTC)


class MongoTableRepository(TableRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, table: Table, session: Any | None = None) -> Table:
        table.updated_at = _now()
        doc = dump_bson(table)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        try:
            await self._db["tables"].replace_one({"_id": table.id}, doc, upsert=True, session=session)
        except DuplicateKeyError:
            raise ConflictError(f"Ya existe una mesa con número {table.number}")
        return table

    async def get(self, table_id, session: Any | None = None) -> Table | None:
        doc = await self._db["tables"].find_one({"_id": table_id}, session=session)
        return load(Table, doc) if doc else None

    async def list(self, active_only: bool = False, session: Any | None = None) -> list[Table]:
        q = {"is_active": True} if active_only else {}
        docs = await self._db["tables"].find(q, session=session).sort("number", 1).to_list(1000)
        return [load(Table, d) for d in docs]


class MongoDeviceRepository(DeviceRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, device: Device, session: Any | None = None) -> Device:
        device.updated_at = _now()
        doc = dump_bson(device)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        try:
            await self._db["devices"].replace_one({"_id": device.id}, doc, upsert=True, session=session)
        except DuplicateKeyError:
            raise ConflictError("Device ya existe")
        return device

    async def get(self, device_id: str, session: Any | None = None) -> Device | None:
        doc = await self._db["devices"].find_one({"_id": device_id}, session=session)
        return load(Device, doc) if doc else None

    async def get_by_token_hash(self, token_hash: str, session: Any | None = None) -> Device | None:
        doc = await self._db["devices"].find_one({"token_hash": token_hash}, session=session)
        return load(Device, doc) if doc else None

    async def get_by_link_code(self, link_code: str, session: Any | None = None) -> Device | None:
        doc = await self._db["devices"].find_one({"link_code": link_code}, session=session)
        return load(Device, doc) if doc else None

    async def list(self, session: Any | None = None) -> list[Device]:
        docs = await self._db["devices"].find({}, session=session).to_list(1000)
        return [load(Device, d) for d in docs]


class MongoTableSessionRepository(TableSessionRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, session_obj: TableSession, session: Any | None = None) -> TableSession:
        doc = dump_bson(session_obj)
        doc["_id"] = doc.pop("id")
        try:
            await self._db["table_sessions"].replace_one(
                {"_id": session_obj.id}, doc, upsert=True, session=session
            )
        except DuplicateKeyError:
            # unique partial index (table_id + status=open)
            raise ConflictError("La mesa ya tiene una sesión abierta (P1: una sola a la vez)")
        return session_obj

    async def get(self, session_id: str, session: Any | None = None) -> TableSession | None:
        doc = await self._db["table_sessions"].find_one({"_id": session_id}, session=session)
        return load(TableSession, doc) if doc else None

    async def find_open_by_table(self, table_id, session: Any | None = None) -> TableSession | None:
        doc = await self._db["table_sessions"].find_one(
            {"table_id": table_id, "status": "open"}, session=session
        )
        return load(TableSession, doc) if doc else None

    async def list_by_table(self, table_id: str, session: Any | None = None) -> list[TableSession]:
        docs = (
            await self._db["table_sessions"].find({"table_id": table_id}, session=session)
            .sort("opened_at", -1).to_list(500)
        )
        return [load(TableSession, d) for d in docs]


class MongoCustomerSessionRepository(CustomerSessionRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, cs: CustomerSession, session: Any | None = None) -> CustomerSession:
        doc = dump_bson(cs)
        doc["_id"] = doc.pop("id")
        try:
            await self._db["customer_sessions"].replace_one(
                {"_id": cs.id}, doc, upsert=True, session=session
            )
        except DuplicateKeyError:
            raise ConflictError("CustomerSession ya existe")
        return cs

    async def get(self, cs_id: str, session: Any | None = None) -> CustomerSession | None:
        doc = await self._db["customer_sessions"].find_one({"_id": cs_id}, session=session)
        return load(CustomerSession, doc) if doc else None

    async def get_by_token_hash(self, token_hash: str, session: Any | None = None) -> CustomerSession | None:
        doc = await self._db["customer_sessions"].find_one(
            {"token_hash": token_hash, "status": "open"}, session=session
        )
        return load(CustomerSession, doc) if doc else None

    async def list_by_table_session(self, table_session_id: str, session: Any | None = None) -> list[CustomerSession]:
        docs = (
            await self._db["customer_sessions"]
            .find({"table_session_id": table_session_id}, session=session)
            .sort("opened_at", -1).to_list(500)
        )
        return [load(CustomerSession, d) for d in docs]
