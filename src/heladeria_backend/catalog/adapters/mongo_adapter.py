"""Repositorios Mongo del módulo catálogo."""

from datetime import UTC, datetime
from typing import Any

import structlog
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from heladeria_backend.catalog.domain.catalog import CatalogItem, Product
from heladeria_backend.catalog.domain.ports import (
    CatalogItemRepository,
    ProductRepository,
)
from heladeria_backend.shared.adapters.outbound.persistence.mongo.repo_mixins import (
    dump_bson,
    load,
)
from heladeria_backend.shared.domain.errors import ConflictError

logger = structlog.get_logger()


def _utcnow():
    return datetime.now(UTC)


class MongoProductRepository(ProductRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, product: Product, session: Any | None = None) -> Product:
        product.updated_at = _utcnow()
        doc = dump_bson(product)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        try:
            await self._db["products"].replace_one(
                {"_id": product.id}, doc, upsert=True, session=session
            )
        except DuplicateKeyError:
            raise ConflictError(f"Producto {product.id} ya existe")
        return product

    async def get(self, product_id: str, session: Any | None = None) -> Product | None:
        doc = await self._db["products"].find_one({"_id": product_id}, session=session)
        return load(Product, doc) if doc else None

    async def list(self, active_only: bool = False, session: Any | None = None) -> list[Product]:
        q = {"is_active": True} if active_only else {}
        docs = await self._db["products"].find(q, session=session).sort("name", 1).to_list(1000)
        return [load(Product, d) for d in docs]


class MongoCatalogItemRepository(CatalogItemRepository):
    def __init__(self, client: AsyncMongoClient, database_name: str):
        self._client = client
        self._db = client[database_name]

    async def save(self, item: CatalogItem, session: Any | None = None) -> CatalogItem:
        item.updated_at = _utcnow()
        doc = dump_bson(item)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        try:
            await self._db["catalog_items"].replace_one(
                {"_id": item.id}, doc, upsert=True, session=session
            )
        except DuplicateKeyError:
            raise ConflictError(f"Item {item.id} ya existe")
        return item

    async def get(self, item_id: str, session: Any | None = None) -> CatalogItem | None:
        doc = await self._db["catalog_items"].find_one({"_id": item_id}, session=session)
        return load(CatalogItem, doc) if doc else None

    async def list(self, active_only: bool = False, session: Any | None = None) -> list[CatalogItem]:
        q = {"is_active": True} if active_only else {}
        docs = await self._db["catalog_items"].find(q, session=session).sort("name", 1).to_list(1000)
        return [load(CatalogItem, d) for d in docs]
