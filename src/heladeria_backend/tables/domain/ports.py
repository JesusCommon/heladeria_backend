"""Puertos de Tables."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from heladeria_backend.tables.domain.tables import (
    CustomerSession,
    Device,
    Table,
    TableSession,
)

class TableRepository(ABC):
    @abstractmethod
    async def save(self, table: Table, session: Any | None = None) -> Table: ...

    @abstractmethod
    async def get(self, table_id: str, session: Any | None = None) -> Table | None: ...

    @abstractmethod
    async def list(self, active_only: bool = False, session: Any | None = None) -> list[Table]: ...


class DeviceRepository(ABC):
    @abstractmethod
    async def save(self, device: Device, session: Any | None = None) -> Device: ...

    @abstractmethod
    async def get(self, device_id: str, session: Any | None = None) -> Device | None: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str, session: Any | None = None) -> Device | None: ...

    @abstractmethod
    async def get_by_link_code(self, link_code: str, session: Any | None = None) -> Device | None: ...

    @abstractmethod
    async def list(self, session: Any | None = None) -> list[Device]: ...


class TableSessionRepository(ABC):
    @abstractmethod
    async def save(self, session_obj: TableSession, session: Any | None = None) -> TableSession: ...

    @abstractmethod
    async def get(self, session_id: str, session: Any | None = None) -> TableSession | None: ...

    @abstractmethod
    async def find_open_by_table(self, table_id: str, session: Any | None = None) -> TableSession | None: ...

    @abstractmethod
    async def list_by_table(self, table_id: str, session: Any | None = None) -> list[TableSession]: ...


class CustomerSessionRepository(ABC):
    @abstractmethod
    async def save(self, cs: CustomerSession, session: Any | None = None) -> CustomerSession: ...

    @abstractmethod
    async def get(self, cs_id: str, session: Any | None = None) -> CustomerSession | None: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str, session: Any | None = None) -> CustomerSession | None: ...

    @abstractmethod
    async def list_by_table_session(self, table_session_id: str, session: Any | None = None) -> list[CustomerSession]: ...
