"""API de inventario administrativa."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from heladeria_backend.identity.adapters.api_security import (
    container,
    require_owner,
    require_staff,
)
from heladeria_backend.identity.domain.identity import Principal
from heladeria_backend.inventory.application.use_cases import (
    adjust,
    create_item,
    get_availability,
    list_items,
    list_movements,
    list_reservations,
    register_entry,
    update_item,
)
from heladeria_backend.inventory.domain.inventory import ReservationState

router = APIRouter(prefix="/admin/inventory", tags=["admin-inventory"])


class ItemCreateDTO(BaseModel):
    name: str = Field(min_length=1)
    unit: Literal["g", "ml", "unit"]
    stock_quantity: int = Field(default=0, ge=0)
    minimum_stock: int = Field(default=0, ge=0)
    track_stock: bool = True


class ItemUpdateDTO(BaseModel):
    name: str | None = None
    minimum_stock: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    track_stock: bool | None = None


class EntryDTO(BaseModel):
    quantity: int = Field(gt=0)
    reason: str | None = None


class AdjustmentDTO(BaseModel):
    delta: int
    reason: str = Field(min_length=1)


def _out(i, available):
    return {
        "id": i.id,
        "name": i.name,
        "unit": i.unit,
        "stock_quantity": i.stock_quantity,
        "reserved_quantity": i.reserved_quantity,
        "available_quantity": available,
        "minimum_stock": i.minimum_stock,
        "is_active": i.is_active,
        "track_stock": i.track_stock,
        "low_stock": i.track_stock and available <= i.minimum_stock,
    }


@router.post("/items", status_code=201)
async def post_item(dto: ItemCreateDTO, request: Request, actor: Annotated[Principal, Depends(require_owner)]):
    c = container(request)
    item = await _create_item(c, dto, actor)
    return _out(item, 0 if not item.track_stock else item.available)


async def _create_item(c, dto: ItemCreateDTO, actor: Principal):
    from heladeria_backend.inventory.application.use_cases import InventoryContext

    ctx = InventoryContext(items=c.inventory_items, movements=c.movements, reservations=c.reservations, clock=c.clock)
    return await create_item(ctx, dto.name, dto.unit, dto.stock_quantity,
                             dto.minimum_stock, dto.track_stock)


@router.get("/items")
async def get_items(request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    items = await list_items(_ctx(c), active_only=False)
    return [_out(i, i.available) for i in items]


@router.patch("/items/{item_id}")
async def patch_item(
    item_id: str,
    dto: ItemUpdateDTO,
    request: Request,
    _: Annotated[Principal, Depends(require_owner)],
):
    c = container(request)
    item = await update_item(_ctx(c), item_id, **dto.model_dump())
    return _out(item, item.available)


@router.post("/items/{item_id}/entries")
async def post_entry(
    item_id: str,
    dto: EntryDTO,
    request: Request,
    actor: Annotated[Principal, Depends(require_owner)],
):
    c = container(request)
    item = await register_entry(_ctx(c), item_id, dto.quantity, actor=actor.sub, reason=dto.reason)
    return _out(item, item.available)


@router.post("/items/{item_id}/adjustments")
async def post_adjustment(
    item_id: str,
    dto: AdjustmentDTO,
    request: Request,
    actor: Annotated[Principal, Depends(require_owner)],
):
    c = container(request)
    item = await adjust(_ctx(c), item_id, dto.delta, actor=actor.sub, reason=dto.reason)
    return _out(item, item.available)


@router.get("/items/{item_id}")
async def get_item(item_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    item = await get_availability(_ctx(c), item_id)
    return _out(item, item.available)


@router.get("/items/{item_id}/movements")
async def get_movements(item_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    movements = await list_movements(_ctx(c), item_id)
    return [
        {
            "id": m.id,
            "inventory_item_id": m.inventory_item_id,
            "quantity": m.quantity,
            "type": m.type.value,
            "order_id": m.order_id,
            "actor": m.actor,
            "reason": m.reason,
            "occurred_at": m.occurred_at.isoformat(),
        }
        for m in movements
    ]


@router.get("/reservations")
async def get_reservations(
    request: Request,
    _: Annotated[Principal, Depends(require_staff)],
    statuses: str = "active,released,expired,consumed",
) -> list[dict]:
    c = container(request)
    wanted = [s.strip() for s in statuses.split(",") if s.strip()]
    state_list = [ReservationState(s) for s in wanted]
    reservations = await list_reservations(_ctx(c), state_list)
    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "status": r.status.value,
            "lines": [ln.model_dump() for ln in r.lines],
            "created_at": r.created_at.isoformat(),
            "expires_at": r.expires_at.isoformat(),
        }
        for r in reservations
    ]


def _ctx(c):
    from heladeria_backend.inventory.application.use_cases import InventoryContext

    return InventoryContext(items=c.inventory_items, movements=c.movements,
                            reservations=c.reservations, clock=c.clock)
