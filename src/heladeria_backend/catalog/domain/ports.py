"""Puertos y repositorios del catálogo."""

from abc import ABC, abstractmethod
from typing import Any

from heladeria_backend.catalog.domain.catalog import CatalogItem, Product


class ProductRepository(ABC):
    @abstractmethod
    async def save(self, product: Product, session: Any | None = None) -> Product: ...

    @abstractmethod
    async def get(self, product_id: str, session: Any | None = None) -> Product | None: ...

    @abstractmethod
    async def list(self, active_only: bool = False, session: Any | None = None) -> list[Product]: ...


class CatalogItemRepository(ABC):
    @abstractmethod
    async def save(self, item: CatalogItem, session: Any | None = None) -> CatalogItem: ...

    @abstractmethod
    async def get(self, item_id: str, session: Any | None = None) -> CatalogItem | None: ...

    @abstractmethod
    async def list(self, active_only: bool = False, session: Any | None = None) -> list[CatalogItem]: ...
