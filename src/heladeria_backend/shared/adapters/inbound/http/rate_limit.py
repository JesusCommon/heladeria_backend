"""Limitador de intentos fallidos en memoria (ventana deslizante).

Emplea una política de "lockout tras N fallos": solo se cuentan los intentos
que fallaron (contraseña errónea, código de vinculación inválido). Un flujo
legítimo nunca llega al bloqueo, mientras que la fuerza bruta queda contenida.

Alcance: por proceso/pod. En despliegues multi-instancia conviene un almacén
compartido (p. ej. Redis) con la misma interfaz.
"""

from collections import deque
from time import monotonic

from fastapi import HTTPException, Request


class FailedAttemptLimiter:
    """Cuenta fallos por clave y bloquea tras `max_attempts` en `window_seconds`."""

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._events: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> None:
        dq = self._events.get(key)
        if dq is None:
            return
        while dq and now - dq[0] > self._window:
            dq.popleft()
        if not dq:
            del self._events[key]

    def allowed(self, key: str) -> bool:
        now = monotonic()
        self._prune(key, now)
        return len(self._events.get(key, ())) < self._max

    def record(self, key: str) -> None:
        now = monotonic()
        self._events.setdefault(key, deque()).append(now)
        self._prune(key, now)

    def reset(self, key: str) -> None:
        self._events.pop(key, None)


def assert_allowed(limiter: FailedAttemptLimiter, key: str) -> None:
    """Lanza 429 si la clave superó el límite de intentos fallidos."""
    if not limiter.allowed(key):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Inténtalo de nuevo más tarde.",
        )


def client_ip(request: Request) -> str:
    """IP del cliente directo. No se confía en X-Forwarded-For (spoofable);
    un proxy inverso debe normalizarla o el operador ajustar esta función."""
    return request.client.host if request.client else "unknown"
