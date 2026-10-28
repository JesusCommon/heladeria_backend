import re
import uuid
import structlog

_CORRELATION_KEY = "correlation_id"
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9\-_.:]{1,128}$")

def generate_correlation_id() -> str:
    return str(uuid.uuid4())

def sanitize_correlation_id(value: str | None) -> str:
    if value and _SAFE_CORRELATION_ID.match(value):
        return value
    return generate_correlation_id()

def bind_correlation_id(value: str) -> None:
    structlog.contextvars.bind_contextvars(**{_CORRELATION_KEY: value})

def clear_context() -> None:
    structlog.contextvars.clear_contextvars()

def get_correlation_id() -> str | None:
    return structlog.contextvars.get_contextvars().get(_CORRELATION_KEY)