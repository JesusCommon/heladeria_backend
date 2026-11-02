"""Puerto dominio-para-tiempo y su adaptador (reloj de sistema / UTC)."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime


class ClockPort(ABC):
    @abstractmethod
    def now(self) -> datetime:
        raise NotImplementedError


class SystemClock(ClockPort):
    def now(self) -> datetime:
        return datetime.now(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)
