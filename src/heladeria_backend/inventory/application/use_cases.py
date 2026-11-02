"""Casos de uso del módulo Inventory."""

from dataclasses import dataclass

from heladeria_backend.inventory.domain.inventory import (
    UNITS,
    InventoryItem,
    InventoryMovement,
    MovementType,
    Reservation,
    ReservationState,
)
from heladeria_backend.inventory.domain.ports import (
    InventoryItemRepository,
    MovementRepository,
    ReservationRepository,
)
from heladeria_backend.shared.domain.clock import ClockPort
from heladeria_backend.shared.domain.errors import (
    DomainValidationError,
    NotFoundError,
)


@dataclass
class InventoryContext:
    items: InventoryItemRepository
    movements: MovementRepository
    reservations: ReservationRepository
    clock: ClockPort


async def create_item(ctx: InventoryContext, name: str, unit: UNITS,
                      stock_quantity: int = 0, minimum_stock: int = 0,
                      track_stock: bool = True) -> InventoryItem:
    if minimum_stock < 0 or stock_quantity < 0:
        raise DomainValidationError("Cantidades no pueden ser negativas")
    item = InventoryItem(
        name=name, unit=unit, stock_quantity=stock_quantity,
        reserved_quantity=0, minimum_stock=minimum_stock, is_active=True,
        track_stock=track_stock,
    )
    await ctx.items.create(item)
    if stock_quantity > 0:
        await _movement(ctx, item.id, stock_quantity, MovementType.ENTRY, actor="seed", reason="Existencias iniciales")
    return item


async def update_item(ctx: InventoryContext, item_id: str, **fields) -> InventoryItem:
    item = await ctx.items.get(item_id)
    if not item:
        raise NotFoundError(f"Inventario {item_id} no existe")
    for key, value in fields.items():
        if value is not None and key in {"minimum_stock", "is_active", "track_stock", "name"}:
            if key == "minimum_stock" and value < 0:
                raise DomainValidationError("minimum_stock no puede ser negativo")
            setattr(item, key, value)
    await ctx.items.update(item)
    return item


async def register_entry(ctx: InventoryContext, item_id: str, quantity: int,
                         actor: str | None = None, reason: str | None = None) -> InventoryItem:
    if quantity <= 0:
        raise DomainValidationError("La entrada debe ser cantidades positivas")
    item = await ctx.items.get(item_id)
    if not item:
        raise NotFoundError(f"Inventario {item_id} no existe")
    item.stock_quantity += quantity
    await ctx.items.update(item)
    await _movement(ctx, item_id, quantity, MovementType.ENTRY, actor=actor, reason=reason or "Entrada de inventario")
    return item


async def adjust(ctx: InventoryContext, item_id: str, delta: int,
                 actor: str | None, reason: str | None) -> InventoryItem:
    if reason is None or not reason.strip():
        raise DomainValidationError("El ajuste exige motivo")
    item = await ctx.items.get(item_id)
    if not item:
        raise NotFoundError(f"Inventario {item_id} no existe")
    if item.stock_quantity + delta < 0:
        raise DomainValidationError("El ajuste llevaría el stock a negativo")
    item.stock_quantity += delta
    await ctx.items.update(item)
    await _movement(ctx, item_id, delta, MovementType.ADJUSTMENT, actor=actor, reason=reason)
    return item


async def get_availability(ctx: InventoryContext, item_id: str) -> InventoryItem:
    item = await ctx.items.get(item_id)
    if not item:
        raise NotFoundError(f"Inventario {item_id} no existe")
    return item


async def list_items(ctx: InventoryContext, active_only: bool = False) -> list[InventoryItem]:
    return await ctx.items.list(active_only)


async def list_movements(ctx: InventoryContext, item_id: str, limit: int = 100) -> list[InventoryMovement]:
    return await ctx.movements.list_by_item(item_id, limit)


async def list_reservations(ctx: InventoryContext, statuses: list[ReservationState] | None = None) -> list[Reservation]:
    return await ctx.reservations.list_statuses(statuses or [])


async def _movement(ctx: InventoryContext, item_id: str, quantity: int,
                    mtype: MovementType, actor: str | None, reason: str) -> None:
    movement = InventoryMovement(
        inventory_item_id=item_id,
        quantity=quantity,
        type=mtype,
        actor=actor,
        reason=reason,
    )
    await ctx.movements.append(movement)
