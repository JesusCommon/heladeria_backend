"""Puertos de salida del módulo Inventory.

Contratoseggies que consumen los casos de uso; la sesión de Mongo se
propaga EXPLÍCITAMENTE: toda operación transaccional recibe `session`.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from heladeria_backend.inventory.domain.inventory import (
    InventoryItem,
    InventoryMovement,
    MovementType,
    Reservation,
)


class InventoryItemRepository(ABC):
    @abstractmethod
    async def create(self, item: InventoryItem, session: Any | None = None) -> InventoryItem: ...

    @abstractmethod
    async def get(self, item_id: str, session: Any | None = None) -> InventoryItem | None: ...

    @abstractmethod
    async def update(self, item: InventoryItem, session: Any | None = None) -> InventoryItem: ...

    @abstractmethod
    async def list(self, active_only: bool = False, session: Any | None = None) -> list[InventoryItem]: ...


class MovementRepository(ABC):
    @abstractmethod
    async def append(
        self,
        movement: InventoryMovement,
        session: Any | None = None,
    ) -> InventoryMovement: ...

    @abstractmethod
    async def list_by_item(
        self,
        item_id: str,
        limit: int = 100,
        session: Any | None = None,
    ) -> list[InventoryMovement]: ...


class ReservationRepository(ABC):
    @abstractmethod
    async def create(self, reservation: Reservation, session: Any | None = None) -> Reservation: ...

    @abstractmethod
    async def get(self, reservation_id: str, session: Any | None = None) -> Reservation | None: ...

    @abstractmethod
    async def get_by_order(self, order_id: str, session: Any | None = None) -> Reservation | None: ...

    @abstractmethod
    async def update(self, reservation: Reservation, session: Any | None = None) -> Reservation: ...

    @abstractmethod
    async def find_active_expired(
        self,
        now: datetime,
        session: Any | None = None,
    ) -> list[Reservation]: ...

    @abstractmethod
    async def list_statuses(
        self,
        statuses: list["ReservationState"],
        session: Any | None = None,
    ) -> list["Reservation"]: ...


class InventoryAtomicPort(ABC):
    """Operaciones atómicas de stock, pensadas para ejecutarse dentro
    de una transacción cuya sesión se propaga explícitamente.

    `reserve` NO debe hacerse "consultar y luego reservar": la condición de
    disponibilidad vive en el filtro del update atómico.
    """

    @abstractmethod
    async def reserve(
        self,
        lines: dict[str, int],
        order_id: str,
        actor: str | None,
        session: Any,
    ) -> None:
        """Reserva cantidades: available = stock - reserved >= requerido.
        Falla (NotEnoughStockError) si algún elemento no alcanza o está
        inactivo; la operación se aborta completa (todo o nada)."""

    @abstractmethod
    async def consume(self, lines: dict[str, int], order_id: str, actor: str | None, session: Any) -> None:
        """Consume definitivamente: stock -= q, reserved -= q."""

    @abstractmethod
    async def release(self, lines: dict[str, int], order_id: str, actor: str | None, session: Any) -> None:
        """Libera reserva: reserved -= q."""
