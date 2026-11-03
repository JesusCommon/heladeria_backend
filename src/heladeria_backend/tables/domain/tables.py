"""Dominio de Tables: mesa física, dispositivos y sesiones."""

import secrets
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from heladeria_backend.shared.domain.mixins import TimestampMixin


def new_id() -> str:
    return str(uuid.uuid4())


class TableStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    DISABLED = "disabled"


class Table(TimestampMixin):
    id: str = Field(default_factory=new_id)
    number: int = Field(gt=0)
    name: str | None = None
    status: TableStatus = TableStatus.CLOSED
    is_active: bool = True


class Device(TimestampMixin):
    id: str = Field(default_factory=new_id)
    name: str | None = None
    linked_table_id: str | None = None
    is_active: bool = True
    # Un código de vinculación de un solo uso emitido por el OWNER, con expiración
    link_code: str | None = None
    link_expires_at: datetime | None = None
    # token sha256 hash; el en claro NUNCA se persiste
    token_hash: str | None = None


class TableSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class TableSession(BaseModel):
    id: str = Field(default_factory=new_id)
    table_id: str
    status: TableSessionStatus = TableSessionStatus.OPEN
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None


class CustomerSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CustomerSession(BaseModel):
    id: str = Field(default_factory=new_id)
    table_session_id: str
    device_id: str
    status: CustomerSessionStatus = CustomerSessionStatus.OPEN
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    token_hash: str | None = None


def generate_link_code() -> str:
    """Código de vinculación de un solo uso.

    12 caracteres hex = 2^48 (~2.8·10^14) combinaciones: suficiente para
    resistir fuerza bruta dentro de su ventana de vida (10 min) incluso
    combinado con el rate limit del endpoint de claim.
    """
    return "".join(secrets.choice("0123456789ABCDEF") for _ in range(12))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)
