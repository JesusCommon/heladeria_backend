"""API de mesas, dispositivos y sesiones."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from heladeria_backend.config.settings import settings
from heladeria_backend.identity.adapters.api_security import (
    container,
    require_owner,
    require_staff,
)
from heladeria_backend.identity.domain.identity import Principal
from heladeria_backend.shared.domain.errors import AuthError
from heladeria_backend.shared.domain.helpers import sha256_hex

router = APIRouter(prefix="/admin/tables", tags=["admin-tables"])


class TableIn(BaseModel):
    number: int = Field(gt=0)
    name: str | None = None


class TablePatch(BaseModel):
    number: int | None = Field(default=None, gt=0)
    name: str | None = None
    is_active: bool | None = None


class DeviceLinkIn(BaseModel):
    table_id: str
    device_name: str | None = None


def _t(t):
    return {"id": t.id, "number": t.number, "name": t.name, "status": t.status.value, "is_active": t.is_active}


@router.post("", status_code=201)
async def create_table(dto: TableIn, request: Request, _: Annotated[Principal, Depends(require_owner)]):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import create_table as uc
    table = await uc(c.tables_ctx, dto.number, dto.name)
    return _t(table)


@router.get("")
async def list_tables(request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import list_tables as uc
    return [_t(t) for t in await uc(c.tables_ctx, active_only=False)]


@router.patch("/{table_id}")
async def patch_table(
    table_id: str, dto: TablePatch, request: Request, _: Annotated[Principal, Depends(require_owner)]
):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import update_table as uc
    table = await uc(c.tables_ctx, table_id, dto.number, dto.name, dto.is_active)
    return _t(table)


@router.post("/{table_id}/sessions/open", status_code=201)
async def open_session(table_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import open_table_session as uc
    ts = await uc(c.tables_ctx, table_id)
    return {"id": ts.id, "table_id": ts.table_id, "status": ts.status.value, "opened_at": ts.opened_at.isoformat()}


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str, request: Request, _: Annotated[Principal, Depends(require_staff)]):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import close_table_session as uc
    ts = await uc(c.tables_ctx, session_id)
    return {"id": ts.id, "status": ts.status.value, "closed_at": (ts.closed_at.isoformat() if ts.closed_at else None)}


@router.post("/devices", status_code=201)
async def create_device_link(
    dto: DeviceLinkIn, request: Request, _: Annotated[Principal, Depends(require_owner)]
):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import create_device_link as uc
    device, code = await uc(c.tables_ctx, dto.table_id, settings.security.device_link_ttl_minutes, dto.device_name)
    return {
        "id": device.id,
        "table_id": device.linked_table_id,
        "link_code": code,
        "expires_at": device.link_expires_at.isoformat(),
    }


@router.delete("/devices/{device_id}", status_code=204)
async def deactivate_device(device_id: str, request: Request, _: Annotated[Principal, Depends(require_owner)]):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import deactivate_device as uc
    await uc(c.tables_ctx, device_id)


# --------------------- rutas de dispositivo ------------------------------

public_router = APIRouter(prefix="/device", tags=["device"])


class ClaimIn(BaseModel):
    link_code: str


class CustomerSessionOut(BaseModel):
    customer_session_id: str
    customer_token: str
    table_session_id: str


@public_router.post("/claim", status_code=200)
async def claim_device(dto: ClaimIn, request: Request):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import claim_device_link as uc
    device, token = await uc(c.tables_ctx, dto.link_code)
    return {"device_id": device.id, "table_id": device.linked_table_id, "device_token": token}


@public_router.post("/customer-session", status_code=201)
async def open_customer_session(
    request: Request,
    x_device_token: Annotated[str, Header()],
):
    c = container(request)
    from heladeria_backend.tables.application.use_cases import open_customer_session as uc
    cs, token = await uc(c.tables_ctx, x_device_token)
    return {
        "customer_session_id": cs.id,
        "customer_token": token,
        "table_session_id": cs.table_session_id,
        "opened_at": cs.opened_at.isoformat(),
    }


@public_router.post("/customer-session/close")
async def close_customer_session(
    request: Request,
    x_customer_token: Annotated[str, Header()],
):
    c = container(request)
    cs = await c.tables_ctx.customer_sessions.get_by_token_hash(sha256_hex(x_customer_token))
    if cs is None:
        raise AuthError("Sesión de cliente inválida")
    from heladeria_backend.tables.application.use_cases import close_customer_session as uc
    cs = await uc(c.tables_ctx, cs.id)
    return {"customer_session_id": cs.id, "status": cs.status.value}
