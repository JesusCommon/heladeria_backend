"""Puertos del módulo Orders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from heladeria_backend.orders.domain.order import IdempotencyRecord, Order, OrderStatus


class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order, session: Any | None = None) -> Order: ...

    @abstractmethod
    async def get(self, order_id: str, session: Any | None = None) -> Order | None: ...

    @abstractmethod
    async def get_by_idempotency_key(
        self, key: str, customer_session_id: str, session: Any | None = None
    ) -> Order | None: ...

    @abstractmethod
    async def list(
        self,
        status: OrderStatus | None = None,
        table_id: str | None = None,
        customer_session_id: str | None = None,
        session: Any | None = None,
    ) -> list[Order]: ...

    @abstractmethod
    async def list_pending_created_before(
        self, cutoff: datetime, session: Any | None = None
    ) -> list[Order]: ...


class IdempotencyRepository(ABC):
    @abstractmethod
    async def insert(
        self, record: IdempotencyRecord, session: Any
    ) -> None:
        """Insert con índice único (key, customer_session_id).
        DuplicateKeyError significa que otra operación ya reservó la clave."""

    @abstractmethod
    async def find(
        self, key: str, customer_session_id: str, session: Any | None = None
    ) -> IdempotencyRecord | None: ...

    @abstractmethod
    async def renew(
        self, key: str, customer_session_id: str, expires_at: datetime, session: Any
    ) -> None: ...

    @abstractmethod
    async def update_order_id(
        self, key: str, customer_session_id: str, order_id: str, session: Any
    ) -> None: ...


class OrderNumberPort(ABC):
    @abstractmethod
    async def next_number(self, session: Any) -> int: ...
