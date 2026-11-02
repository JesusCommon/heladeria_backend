"""Helpers de serialización Pydantic <-> BSON.

- dump_bson con `mode="python"` preserva datetime para BSON.
- carga con model_validate para reconstruir modelos desde documentos.
"""

from datetime import timezone
from typing import Any, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def dump_bson(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="python")


def _normalise(value: Any) -> Any:
    """Normaliza datetimes naive (leídos con tz_aware=False) a UTC aware."""
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    import datetime as _dt

    if isinstance(value, _dt.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value


def load(model_class: Type[T], doc: dict[str, Any]) -> T:
    data = dict(doc)
    if "_id" in data and "id" not in data:
        data["id"] = data.pop("_id")
        data["_id"] = data["id"]  # compat: el modelo nombrará id
        data.pop("_id", None)
    return model_class.model_validate(_normalise(data))
