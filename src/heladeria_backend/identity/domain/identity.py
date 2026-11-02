"""Módulo Identity & Access: usuario administrador, hash y tokens."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
import uuid

from pydantic import BaseModel, Field

from heladeria_backend.shared.domain.mixins import TimestampMixin


class Role(StrEnum):
    OWNER = "owner"
    STAFF = "staff"


class AdminUser(TimestampMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str = Field(min_length=1)
    password_hash: str
    role: Role
    is_active: bool = True


class Principal(BaseModel):
    """Identidad autenticada (JWT claims decodificados)."""

    sub: str
    role: Role
    exp: datetime
