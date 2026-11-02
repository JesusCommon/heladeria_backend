"""Dominio de inventario: elementos, reservas y movimientos."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from heladeria_backend.shared.domain.mixins import TimestampMixin

UNITS = Literal["g", "ml", "unit"]


def new_id() -> str:
    return str(uuid.uuid4())


class InventoryItem(TimestampMixin):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1)
    unit: UNITS
    stock_quantity: int = Field(ge=0)
    reserved_quantity: int = Field(default=0, ge=0)
    minimum_stock: int = Field(default=0, ge=0)
    is_active: bool = True
    # track_stock=False significa "no controla existencias" (siempre disponible)
    track_stock: bool = True
    version: int = 0

    @property
    def available(self) -> int | float:
        """Stock físico - reservado; si no controla stock, ilimitado."""
        if not self.track_stock:
            return float("inf")
        return self.stock_quantity - self.reserved_quantity

    @model_validator(mode="after")
    def _invariants(self) -> "InventoryItem":
        if self.reserved_quantity > self.stock_quantity:
            msg = f"{self.name}: reservado {self.reserved_quantity} > físico {self.stock_quantity}"
            raise ValueError(msg)
        return self


class MovementType(StrEnum):
    ENTRY = "entry"
    CONSUMPTION = "consumption"
    RESERVE = "reserve"
    RELEASE = "release"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    CORRECTION = "correction"


class InventoryMovement(BaseModel):
    """Registro append-only. quantity con signo: + entra, - sale."""

    id: str = Field(default_factory=new_id)
    inventory_item_id: str
    quantity: int
    type: MovementType
    order_id: str | None = None
    actor: str | None = None
    reason: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReservationState(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    RELEASED = "released"
    EXPIRED = "expired"


class ReservationLine(BaseModel):
    inventory_item_id: str
    quantity: int = Field(gt=0)
    unit: UNITS


class Reservation(BaseModel):
    id: str = Field(default_factory=new_id)
    order_id: str
    lines: list[ReservationLine]
    status: ReservationState = ReservationState.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    consumed_at: datetime | None = None
    released_at: datetime | None = None
