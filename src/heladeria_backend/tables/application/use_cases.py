"""Casos de uso de Tables: mesas, dispositivos, sesiones."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from heladeria_backend.shared.domain.clock import ClockPort
from heladeria_backend.shared.domain.errors import (
    AuthError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
    UnavailableError,
)
from heladeria_backend.shared.domain.helpers import sha256_hex
from heladeria_backend.tables.domain.ports import (
    CustomerSessionRepository,
    DeviceRepository,
    TableRepository,
    TableSessionRepository,
)
from heladeria_backend.tables.domain.tables import (
    CustomerSession,
    CustomerSessionStatus,
    Device,
    Table,
    TableSession,
    TableSessionStatus,
    TableStatus,
    generate_link_code,
    generate_session_token,
)

logger = structlog.get_logger()


@dataclass
class TablesContext:
    tables: TableRepository
    devices: DeviceRepository
    table_sessions: TableSessionRepository
    customer_sessions: CustomerSessionRepository
    clock: ClockPort


# ------------------------------ Mesas -------------------------------------

async def create_table(ctx: TablesContext, number: int, name: str | None = None) -> Table:
    if number <= 0:
        raise DomainValidationError("Número de mesa debe ser positivo")
    table = Table(number=number, name=name, status=TableStatus.CLOSED)
    await ctx.tables.save(table)
    return table


async def update_table(ctx: TablesContext, table_id: str, number: int | None = None,
                       name: str | None = None, is_active: bool | None = None) -> Table:
    table = await ctx.tables.get(table_id)
    if not table:
        raise NotFoundError(f"Mesa {table_id} no existe")
    if number is not None and number != table.number:
        if number <= 0:
            raise DomainValidationError("Número de mesa debe ser positivo")
        others = [t for t in await ctx.tables.list() if t.id != table_id and t.number == number]
        if others:
            raise ConflictError(f"La mesa n.º {number} ya existe")
        table.number = number
    if name is not None:
        table.name = name
    if is_active is not None:
        table.is_active = is_active
        if not is_active:
            table.status = TableStatus.DISABLED
    await ctx.tables.save(table)
    return table


async def list_tables(ctx: TablesContext, active_only: bool = False) -> list[Table]:
    return await ctx.tables.list(active_only)


# ------------------------- Dispositivos -----------------------------------

async def create_device_link(ctx: TablesContext, table_id: str,
                             ttl_minutes: int, device_name: str | None = None) -> tuple[Device, str]:
    """OWNER emite un dispositivo NUEVO con un código de vinculación de un solo uso."""
    if await ctx.tables.get(table_id) is None:
        raise NotFoundError(f"Mesa {table_id} no existe")
    code = generate_link_code()
    now = ctx.clock.now()
    device = Device(
        name=device_name or f"device-{uuid.uuid4().hex[:8]}",
        linked_table_id=table_id,
        link_code=code,
        link_expires_at=now + timedelta(minutes=ttl_minutes),
        is_active=False,  # se activa al reclamar
    )
    await ctx.devices.save(device)
    return device, code


def _as_aware(dt: datetime) -> datetime:
    """Mongo devuelve fechas naive (tz_aware=False en tests); uniformar a UTC aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def claim_device_link(ctx: TablesContext, code: str) -> tuple[Device, str]:
    """El dispositivo (tablet) reclama el código y obtiene su token definitivo.

    El código es de un solo uso: si el dispositivo ya fue reclamado se avisa
    conflicto (aunque el código siga indexado para dar un mensaje claro)."""
    if not code or not code.strip():
        raise DomainValidationError("Código de vinculación requerido")
    device = await ctx.devices.get_by_link_code(code.strip().upper())
    if device is None:
        raise NotFoundError("Código de vinculación inválido")
    if device.token_hash is not None:
        raise ConflictError("Device ya está vinculado")
    if device.link_expires_at and _as_aware(device.link_expires_at) < ctx.clock.now():
        raise UnavailableError("Código de vinculación expirado")
    token = generate_session_token()
    device.token_hash = sha256_hex(token)
    device.link_code = None  # código quemado: un solo uso
    device.link_expires_at = None
    device.is_active = True
    await ctx.devices.save(device)
    return device, token


async def deactivate_device(ctx: TablesContext, device_id: str) -> Device:
    device = await ctx.devices.get(device_id)
    if not device:
        raise NotFoundError(f"Device {device_id} no existe")
    device.is_active = False
    await ctx.devices.save(device)
    return device


# ---------------------- Sesiones de mesa ----------------------------------

async def open_table_session(ctx: TablesContext, table_id: str) -> TableSession:
    table = await ctx.tables.get(table_id)
    if table is None or not table.is_active:
        raise NotFoundError(f"Mesa {table_id} no existe o inactiva")
    existing = await ctx.table_sessions.find_open_by_table(table_id)
    if existing is not None:
        raise ConflictError("La mesa ya tiene una sesión abierta (P1)")
    ts = TableSession(table_id=table_id)
    await ctx.table_sessions.save(ts)
    table.status = TableStatus.OPEN
    await ctx.tables.save(table)
    return ts


async def close_table_session(ctx: TablesContext, table_session_id: str) -> TableSession:
    ts = await ctx.table_sessions.get(table_session_id)
    if not ts or ts.status != TableSessionStatus.OPEN:
        raise NotFoundError("Sesión de mesa no abierta")
    for cs in await ctx.customer_sessions.list_by_table_session(ts.id):
        cs.status = CustomerSessionStatus.CLOSED
        cs.closed_at = datetime.now(UTC)
        await ctx.customer_sessions.save(cs)
    ts.status = TableSessionStatus.CLOSED
    ts.closed_at = datetime.now(UTC)
    await ctx.table_sessions.save(ts)
    table = await ctx.tables.get(ts.table_id)
    if table:
        table.status = TableStatus.CLOSED
        await ctx.tables.save(table)
    return ts


# ----------------- Sesiones individuales de clientes ----------------------

async def open_customer_session(ctx: TablesContext, device_token: str) -> tuple[CustomerSession, str]:
    """El dispositivo abre su propia sesión individual; el token del device
    se valida por HASH, nunca se confía en ids enviados por el cliente."""
    token_hash = sha256_hex(device_token)
    device = await ctx.devices.get_by_token_hash(token_hash)
    if not device or not device.is_active:
        raise AuthError("Dispositivo no autorizado")
    if not device.linked_table_id:
        raise UnavailableError("Dispositivo sin mesa asociada")
    table_session = await ctx.table_sessions.find_open_by_table(device.linked_table_id)
    if table_session is None or table_session.status != TableSessionStatus.OPEN:
        raise UnavailableError("La mesa no tiene sesión abierta")

    token = generate_session_token()
    cs = CustomerSession(
        table_session_id=table_session.id,
        device_id=device.id,
        token_hash=sha256_hex(token),
    )
    await ctx.customer_sessions.save(cs)
    return cs, token


async def close_customer_session(ctx: TablesContext, customer_session_id: str) -> CustomerSession:
    cs = await ctx.customer_sessions.get(customer_session_id)
    if not cs:
        raise NotFoundError("CustomerSession no existe")
    cs.status = CustomerSessionStatus.CLOSED
    cs.closed_at = datetime.now(UTC)
    await ctx.customer_sessions.save(cs)
    return cs
