"""Helpers de serialización Pydantic <-> BSON.

- dump_bson con `mode="python"` preserva datetime para BSON.
- carga con model_validate para reconstruir modelos desde documentos.
"""

from typing import Any, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def dump_bson(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="python")


def load(model_class: Type[T], doc: dict[str, Any]) -> T:
    data = dict(doc)
    if "_id" in data and "id" not in data:
        data["id"] = data.pop("_id")
        data["_id"] = data["id"]  # compat: el modelo nombrará id
        data.pop("_id", None)
    return model_class.model_validate(data)
