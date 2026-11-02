"""Repositorio Mongo de administradores."""

from typing import Any

from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from heladeria_backend.identity.domain.identity import AdminUser
from heladeria_backend.identity.domain.ports import AdminUserRepository
from heladeria_backend.shared.adapters.outbound.persistence.mongo.repo_mixins import (
    dump_bson,
    load,
)
from heladeria_backend.shared.domain.errors import ConflictError


class MongoAdminUserRepository(AdminUserRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, user: AdminUser, session: Any | None = None) -> AdminUser:
        from datetime import UTC, datetime

        user.updated_at = datetime.now(UTC)
        doc = dump_bson(user)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        try:
            await self._db["admin_users"].replace_one(
                {"_id": user.id}, doc, upsert=True, session=session
            )
        except DuplicateKeyError:
            raise ConflictError("Usuario ya existe")
        return user

    async def get_by_username(self, username: str, session: Any | None = None) -> AdminUser | None:
        doc = await self._db["admin_users"].find_one({"username": username}, session=session)
        return load(AdminUser, doc) if doc else None

    async def get(self, user_id: str, session: Any | None = None) -> AdminUser | None:
        doc = await self._db["admin_users"].find_one({"_id": user_id}, session=session)
        return load(AdminUser, doc) if doc else None

    async def exists_any(self, session: Any | None = None) -> bool:
        return await self._db["admin_users"].count_documents({}, session=session) > 0
