"""API de pedidos: cliente (mesa) y administración."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from heladeria_backend.catalog.domain.catalog import SelectionInput
from heladeria_backend.identity.adapters.api_security import (
    container,
    get_admin_principal,
    get_customer_session,
    require_staff,
)
from heladeria_backend.identity.domain.identity import Principal
from heladeria_backend.orders.application.use_cases import (
    LineInput,
    accept_order,
    cancel_order,
    create_order,
    expire_stale_orders,
    get_order,
    list_orders,
    mark_delivered,
    mark_ready,
    start_preparing,
)
from heladeria_backend.orders.domain.order import OrderStatus
from heladeria_backend.tables.application.use_cases import open_customer_session as open_cs_uc
from heladeria_backend.tables.domain.ports import CustomerSessionRepository

router = APIRouter(prefix="/api/orders", tags=["orders"])
admin_router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


class SelectionIn(BaseModel):
    group_id: str
    catalog_item_id: str
    quantity: int = Field(default=1, ge=1)


class LineIn(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)
    selections: list[SelectionIn] = Field(default_factory=list)


class CreateOrderIn(BaseModel):
    lines: list[LineIn] = Field(min_length=1)
    idempotency_key: str = Field(min_length=4, max_length=128)


def _order_out(o) -> dict:
    return {
        "id": o.id,
        "order_number": o.order_number,
        "status": o.status.value,
        "table_id": o.table_id,
        "total": o.total,
        "currency": o.currency,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "accepted_at": o.accepted_at.isoformat() if o.accepted_at else None,
        "completed_at": o.completed_at.isoformat() if o.completed_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
        "cancel_reason": o.cancel_reason,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "base_price": item.base_price,
                "options_price": item.options_price,
                "unit_final_price": item.unit_final_price,
                "subtotal": item.subtotal,
                "selections": [s.model_dump() for s in item.selections],
            }
            for item in o.items
        ],
    }


@router.post("", status_code=201)
async def create(
    dto: CreateOrderIn,
    request: Request,
    cs: Annotated[object, Depends(get_customer_session)],
    idempotency_key_fallback: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    c = container(request)
    # La mesa se deduce SIEMPRE por la cadena servidor: customer_session → table_session → table
    ts = await c.tables_ctx.table_sessions.get(cs.table_session_id)
    if ts is None:
        from heladeria_backend.shared.domain.errors import UnavailableError
        raise UnavailableError("Sesión de mesa inexistente")
    lines = [
        LineInput(
            product_id=l.product_id,
            quantity=l.quantity,
            selections=[
                SelectionInput(group_id=s.group_id, catalog_item_id=s.catalog_item_id, quantity=s.quantity)
                for s in l.selections
            ],
        )
        for l in dto.lines
    ]
    order = await create_order(
        c.orders_deps,
        customer_session_id=cs.id,
        table_session_id=ts.id,
        table_id=ts.table_id,
        idempotency_key=dto.idempotency_key or idempotency_key_fallback or "",
        lines=lines,
    )
    return _order_out(order)


@router.get("/{order_id}")
async def get_my_order(order_id: str, request: Request, cs: Annotated[object, Depends(get_customer_session)]):
    c = container(request)
    order = await get_order(c.orders_deps, order_id)
    if order.customer_session_id != cs.id:
        from heladeria_backend.shared.domain.errors import AuthError
        raise AuthError("Pedido de otro cliente")
    return _order_out(order)


@router.get("")
async def list_my_orders(request: Request, cs: Annotated[object, Depends(get_customer_session)]):
    c = container(request)
    orders = await list_orders(c.orders_deps, customer_session_id=cs.id)
    return [_order_out(o) for o in orders]


@admin_router.get("")
async def admin_list_orders(
    request: Request,
    _: Annotated[Principal, Depends(require_staff)],
    status: str | None = None,
    table_id: str | None = None,
):
    c = container(request)
    st = OrderStatus(status) if status else None
    orders = await list_orders(c.orders_deps, status=st, table_id=table_id)
    return [_order_out(o) for o in orders]


@admin_router.post("/{order_id}/accept")
async def admin_accept(order_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    return _order_out(await accept_order(c.orders_deps, order_id))


@admin_router.post("/{order_id}/preparing")
async def admin_preparing(order_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    return _order_out(await start_preparing(c.orders_deps, order_id))


@admin_router.post("/{order_id}/ready")
async def admin_ready(order_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    return _order_out(await mark_ready(c.orders_deps, order_id))


@admin_router.post("/{order_id}/delivered")
async def admin_delivered(order_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    return _order_out(await mark_delivered(c.orders_deps, order_id))


@admin_router.post("/{order_id}/cancel")
async def admin_cancel(
    order_id: str,
    request: Request,
    _: Annotated[Principal, Depends(require_staff)],
    reason: str = "cancelado por staff",
):
    c = container(request)
    return _order_out(await cancel_order(c.orders_deps, order_id, reason))


@admin_router.post("/maintenance/expire")
async def admin_expire(request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    expired = await expire_stale_orders(c.orders_deps)
    return {"expired_order_ids": expired}
