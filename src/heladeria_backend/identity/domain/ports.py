"""Puertos de salida de Identity."""

from abc import ABC, abstractmethod
from typing import Any

from heladeria_backend.identity.domain.identity import AdminUser, Principal


class AdminUserRepository(ABC):
    @abstractmethod
    async def save(self, user: AdminUser, session: Any | None = None) -> AdminUser: ...

    @abstractmethod
    async def get_by_username(self, username: str, session: Any | None = None) -> AdminUser | None: ...

    @abstractmethod
    async def get(self, user_id: str, session: Any | None = None) -> AdminUser | None: ...

    @abstractmethod
    async def exists_any(self, session: Any | None = None) -> bool: ...


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, plain: str) -> str: ...

    @abstractmethod
    def verify(self, plain: str, hashed: str) -> bool: ...


class TokenIssuer(ABC):
    @abstractmethod
    def issue(self, principal: Principal) -> str: ...

    @abstractmethod
    def verify(self, token: str) -> Principal: ...
