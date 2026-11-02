"""Dominio de Orders: agregado pedido + máquina de estados legal."""

from datetime import UTC, datetime
from enum import StrEnum
import uuid

from pydantic import BaseModel, Field, model_validator

from heladeria_backend.shared.domain.errors import ConflictError
from heladeria_backend.shared.domain.mixins import TimestampMixin


class OrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


LEGAL_TRANSITIONS: dict["OrderStatus", set["OrderStatus"]] = {
    OrderStatus.PENDING: {OrderStatus.ACCEPTED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.ACCEPTED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
}


class SelectionSnapshot(BaseModel):
    group_id: str
    group_name: str
    catalog_item_id: str
    option_name: str
    quantity: int = Field(gt=0)
    unit_price: int = Field(ge=0)


class OrderItem(BaseModel):
    """Instantánea inmutable; jamás se muta después de confirmar el pedido."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str
    product_name: str
    base_price: int = Field(ge=0)
    quantity: int = Field(gt=0)
    selections: list[SelectionSnapshot] = Field(default_factory=list)
    options_price: int = Field(ge=0)
    unit_final_price: int = Field(gt=0)
    subtotal: int = Field(gt=0)


class Order(TimestampMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_number: int = Field(gt=0)
    customer_session_id: str
    table_session_id: str
    table_id: str
    status: OrderStatus = OrderStatus.PENDING
    total: int = Field(ge=0)
    currency: str = "COP"
    idempotency_key: str | None = None
    reservation_id: str | None = None
    items: list[OrderItem] = Field(default_factory=list)
    accepted_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None

    @model_validator(mode="after")
    def _check_total(self) -> "Order":
        expected = sum(i.subtotal for i in self.items)
        if self.total != expected:
            raise ValueError(
                f"total {self.total} != suma de subtotales {expected}"
            )
        return self

    def transition(self, new_status: OrderStatus) -> "Order":
        if new_status == self.status:
            # transición idempotente: repetir la misma operación es no-op
            return self
        if new_status not in LEGAL_TRANSITIONS[self.status]:
            raise ConflictError(
                f"Transición ilegal {self.status} → {new_status}"
            )
        self.status = new_status
        now = datetime.now(UTC)
        if new_status is OrderStatus.ACCEPTED:
            self.accepted_at = now
        if new_status is OrderStatus.DELIVERED:
            self.completed_at = now
        if new_status in (OrderStatus.CANCELLED, OrderStatus.EXPIRED):
            self.cancelled_at = now
        self.touch()
        return self


class IdempotencyRecord(BaseModel):
    key: str
    customer_session_id: str
    order_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
