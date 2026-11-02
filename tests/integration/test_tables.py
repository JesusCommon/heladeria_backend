"""Pruebas del módulo Tables contra Mongo real."""


import pytest

from heladeria_backend.shared.domain.errors import (
    AuthError,
    ConflictError,
    NotFoundError,
    UnavailableError,
)
from heladeria_backend.shared.domain.helpers import sha256_hex
from heladeria_backend.tables.application.use_cases import (
    claim_device_link,
    close_table_session,
    create_device_link,
    create_table,
    open_customer_session,
    open_table_session,
    update_table,
)
from heladeria_backend.tables.domain.tables import Device

pytestmark = pytest.mark.integration


async def test_create_table_and_unique_number(container):
    ctx = container.tables_ctx
    await create_table(ctx, 5, "Ventana")
    from heladeria_backend.tables.application.use_cases import create_table as create_table_uc

    with pytest.raises(Exception):  # índice único number
        await create_table_uc(ctx, 5)


async def test_renumber_table_without_touching_history(container):
    ctx = container.tables_ctx
    table = await create_table(ctx, 10)
    ts = await open_table_session(ctx, table.id)
    await update_table(ctx, table.id, number=12)
    refreshed = await ctx.tables.get(table.id)
    assert refreshed.number == 12
    assert refreshed.id == table.id
    # la sesión sigue vigente y ligada al mismo id interno
    still = await ctx.table_sessions.get(ts.id)
    assert still.table_id == table.id


async def test_one_open_session_per_table(container):
    ctx = container.tables_ctx
    t = await create_table(ctx, 21)
    await open_table_session(ctx, t.id)
    with pytest.raises(ConflictError, match="sesión abierta"):
        await open_table_session(ctx, t.id)
    # cerrar permite reabrir
    opened = await ctx.table_sessions.find_open_by_table(t.id)
    await close_table_session(ctx, opened.id)
    await open_table_session(ctx, t.id)


async def test_close_closes_customer_sessions(container):
    ctx = container.tables_ctx
    t = await create_table(ctx, 22)
    ts = await open_table_session(ctx, t.id)
    from heladeria_backend.tables.domain.tables import CustomerSession

    cs = CustomerSession(table_session_id=ts.id, device_id="d", token_hash=sha256_hex("t"))
    await ctx.customer_sessions.save(cs)
    await close_table_session(ctx, ts.id)
    after = await ctx.customer_sessions.get(cs.id)
    assert after.status.value == "closed"
    assert after.closed_at is not None


async def test_device_link_claim_flow(container):
    ctx = container.tables_ctx
    t = await create_table(ctx, 23)
    device, code = await create_device_link(ctx, t.id, ttl_minutes=10, device_name="Tablet-1")
    assert code and device.link_expires_at is not None

    claimed, token = await claim_device_link(ctx, code)
    assert claimed.token_hash == sha256_hex(token)
    # el código es de un solo uso: quemado tras reclamar
    assert claimed.link_code is None
    assert claimed.is_active

    # re-reclamar el código quemado falla limpiamente
    with pytest.raises(NotFoundError):
        await claim_device_link(ctx, code)

    # código inválido
    with pytest.raises(NotFoundError):
        await claim_device_link(ctx, "00000000")


async def test_device_link_code_expires(container):
    ctx = container.tables_ctx
    t = await create_table(ctx, 24)
    device, code = await create_device_link(ctx, t.id, ttl_minutes=-5)
    with pytest.raises(UnavailableError, match="expirado"):
        await claim_device_link(ctx, code)


async def test_customer_session_requires_open_table_session(container):
    ctx = container.tables_ctx
    t = await create_table(ctx, 25)
    # sin sesión abierta
    device = Device(name="x", is_active=True, linked_table_id=t.id)
    device.token_hash = sha256_hex("tok-x")
    await ctx.devices.save(device)
    with pytest.raises(UnavailableError):
        await open_customer_session(ctx, "tok-x")
    # con sesión abierta ya sí
    await open_table_session(ctx, t.id)
    cs, token2 = await open_customer_session(ctx, "tok-x")
    assert cs.device_id == device.id
    # dispositivo inactivo no puede
    device.is_active = False
    await ctx.devices.save(device)
    with pytest.raises(AuthError):
        await open_customer_session(ctx, "tok-x")
