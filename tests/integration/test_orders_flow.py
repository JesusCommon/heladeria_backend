"""Flujo completo de Orders contra Mongo real: creación transaccional,
idempotencia, transiciones, cancelación, expiración, snapshot y concurrencia.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from heladeria_backend.catalog.domain.catalog import (
    CatalogItem,
    ConsumptionRequirement,
    CustomizationGroup,
    GroupOption,
    Product,
    SelectionInput,
)
from heladeria_backend.inventory.domain.inventory import InventoryItem, ReservationState
from heladeria_backend.orders.application.use_cases import (
    LineInput,
    accept_order,
    cancel_order,
    create_order,
    expire_stale_orders,
    list_orders,
    start_preparing,
    transition_order,
)
from heladeria_backend.orders.domain.order import Order, OrderStatus
from heladeria_backend.shared.adapters.outbound.persistence.mongo.unit_of_work import (
    MongoUnitOfWork,
)
from heladeria_backend.shared.domain.errors import ConflictError, NotEnoughStockError
from heladeria_backend.shared.domain.helpers import sha256_hex
from heladeria_backend.tables.domain.tables import CustomerSession, Device, Table
from heladeria_backend.tables.application.use_cases import open_table_session

pytestmark = pytest.mark.integration


def coupon_dummy():  # pragma: no cover
    return None


async def seed_world(container) -> SimpleNamespace:
    choco = str(uuid.uuid4())
    vani = str(uuid.uuid4())

    await container.catalog_items.save(CatalogItem(name="Chocolate", kind="flavor"))
    await container.catalog_items.save(CatalogItem(name="Vainilla", kind="flavor"))

    choco_item = InventoryItem(name="Chocolate", unit="g", stock_quantity=200)
    choco_item.id = choco
    await container.inventory_items.create(choco_item)

    product = Product(
        name="Helado de cono",
        kind="cone",
        base_price=7000,
        customization=[
            CustomizationGroup(
                name="Sabores",
                min_selections=1,
                max_selections=3,
                required=True,
                allow_repeated=True,
                allow_per_option_quantity=True,
                options=[
                    GroupOption(
                        catalog_item_id=choco,
                        additional_price=2500,
                        consumption=[ConsumptionRequirement(inventory_item_id=choco, quantity=100, unit="g")],
                    ),
                    GroupOption(catalog_item_id=vani, additional_price=2500),
                ],
            ),
        ],
    )
    await container.products.save(product)

    table = Table(number=5)
    await container.tables_ctx.tables.save(table)
    ts = await open_table_session(container.tables_ctx, table.id)

    css = []
    for _ in range(2):
        device = Device(name="tablet", is_active=True, linked_table_id=table.id)
        device.token_hash = sha256_hex("tok-" + uuid.uuid4().hex)
        await container.tables_ctx.devices.save(device)
        cs = CustomerSession(
            table_session_id=ts.id,
            device_id=device.id,
            token_hash=sha256_hex("cus-" + uuid.uuid4().hex),
        )
        await container.tables_ctx.customer_sessions.save(cs)
        css.append(cs)

    return SimpleNamespace(
        container=container,
        product=product,
        choco=choco,
        item=choco_item,
        table_session=ts,
        table_id=table.id,
        cs_ids=[c.id for c in css],
    )


@pytest.fixture
async def env(container):
    return await seed_world(container)


def sphere(e, choco_balls=1):
    group = e.product.customization[0]
    return [
        LineInput(
            product_id=e.product.id,
            quantity=1,
            selections=[SelectionInput(group_id=group.id, catalog_item_id=e.choco, quantity=choco_balls)],
        )
    ]


async def _idempotency_count(e) -> int:
    db = e.container.client[e.container.db_name]
    return await db["idempotency_keys"].count_documents({})


async def test_create_order_reserves_and_snapshots(env):
    e = env
    order = await create_order(
        e.container.orders_deps,
        customer_session_id=e.cs_ids[0],
        table_session_id=e.table_session.id,
        table_id=e.table_id,
        idempotency_key="k-1",
        lines=sphere(e, choco_balls=1),
    )
    assert order.status is OrderStatus.PENDING
    assert order.total == 7000 + 2500
    assert order.items[0].selections[0].quantity == 1
    assert order.reservation_id is not None

    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 100
    assert item.stock_quantity == 200

    moves = await e.container.movements.list_by_item(e.choco)
    assert any(m.type.value == "reserve" and m.order_id == order.id for m in moves)


async def test_idempotent_same_key_returns_same_order(env):
    e = env
    deps = e.container.orders_deps
    key = "k-idem-2"
    o1 = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                            table_id=e.table_id, idempotency_key=key, lines=sphere(e))
    o2 = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                            table_id=e.table_id, idempotency_key=key, lines=sphere(e))
    assert o1.id == o2.id
    assert await _idempotency_count(e) == 1
    orders = await list_orders(deps, customer_session_id=e.cs_ids[0])
    assert len(orders) == 1
    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 100


async def test_insufficient_stock_clean_abort(env):
    e = env
    deps = e.container.orders_deps
    it = await e.container.inventory_items.get(e.choco)
    it.stock_quantity = 100
    await e.container.inventory_items.update(it)
    with pytest.raises(NotEnoughStockError):
        await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                           table_id=e.table_id, idempotency_key="k-fail", lines=sphere(e, choco_balls=2))
    assert await list_orders(deps, customer_session_id=e.cs_ids[0]) == []
    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 0
    # rollback total: la clave no quedó registrada
    record = await deps.idempotency.find("k-fail", e.cs_ids[0])
    assert record is None


async def test_cancel_pending_releases_reservation(env):
    e = env
    deps = e.container.orders_deps
    order = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                               table_id=e.table_id, idempotency_key="k-cancel", lines=sphere(e))
    cancelled = await cancel_order(deps, order.id, "cambio de opinión")
    assert cancelled.status is OrderStatus.CANCELLED
    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 0
    reservation = await deps.reservations.get_by_order(order.id)
    assert reservation.status is ReservationState.RELEASED
    # idempotente: re-cancelar no rompe ni re-libera
    again = await cancel_order(deps, order.id, "x")
    assert again.status is OrderStatus.CANCELLED
    # el consumo nunca ocurrió: el stock físico no se toca al cancelar pendiente
    assert item.stock_quantity == 200


async def test_preparing_consumes_reservation_idempotently(env):
    e = env
    deps = e.container.orders_deps
    order = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                               table_id=e.table_id, idempotency_key="k-prep", lines=sphere(e))
    await accept_order(deps, order.id)
    await start_preparing(deps, order.id)
    await start_preparing(deps, order.id)  # segunda llamada idempotente
    item = await e.container.inventory_items.get(e.choco)
    assert item.stock_quantity == 100  # 200 - 100 g consumidos
    assert item.reserved_quantity == 0
    # cancelar post-consumo NO devuelve stock ya consumido
    cancelled = await cancel_order(deps, order.id, "cancel tarde")
    assert cancelled.status is OrderStatus.CANCELLED
    item = await e.container.inventory_items.get(e.choco)
    assert item.stock_quantity == 100  # 200 - 1 bola consumida


async def test_expire_pending_releases_reservation(env):
    e = env
    deps = e.container.orders_deps
    order = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                               table_id=e.table_id, idempotency_key="k-exp", lines=sphere(e))
    db = e.container.client[e.container.db_name]
    await db["reservations"].update_one(
        {"order_id": order.id},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=5)}},
    )
    expired = await expire_stale_orders(deps)
    assert order.id in expired
    refreshed = await deps.orders.get(order.id)
    assert refreshed.status is OrderStatus.EXPIRED
    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 0


async def test_illegal_transitions_rejected(env):
    e = env
    deps = e.container.orders_deps
    order = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                               table_id=e.table_id, idempotency_key="k-ill", lines=sphere(e))
    with pytest.raises(ConflictError):
        await transition_order(deps, order.id, OrderStatus.DELIVERED)
    with pytest.raises(ConflictError):
        await transition_order(deps, order.id, OrderStatus.PREPARING)


async def test_snapshot_immutable_after_price_change(env):
    e = env
    deps = e.container.orders_deps
    order = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                               table_id=e.table_id, idempotency_key="k-snap", lines=sphere(e))
    e.product.base_price = 9000
    e.product.customization[0].options[0].additional_price = 4000
    e.product.customization[0].options[0].is_active = False
    await e.container.products.save(e.product)

    historic = await deps.orders.get(order.id)
    assert historic.items[0].base_price == 7000
    assert historic.items[0].selections[0].unit_price == 2500
    assert historic.total == order.total


async def test_two_customers_same_table_independent_orders(env):
    e = env
    deps = e.container.orders_deps
    o1 = await create_order(deps, customer_session_id=e.cs_ids[0], table_session_id=e.table_session.id,
                            table_id=e.table_id, idempotency_key="k-a", lines=sphere(e, choco_balls=1))
    o2 = await create_order(deps, customer_session_id=e.cs_ids[1], table_session_id=e.table_session.id,
                            table_id=e.table_id, idempotency_key="k-b", lines=sphere(e, choco_balls=1))
    assert o1.customer_session_id != o2.customer_session_id
    orders = await list_orders(deps, table_id=e.table_id)
    assert {o.id for o in orders} == {o1.id, o2.id}


async def test_concurrency_last_unit_single_winner(env):
    """PRUEBA CRÍTICA de la especificación: 100 g; dos clientes 100 g simultáneos."""
    e = env
    deps = e.container.orders_deps
    # exactamente 100 g disponibles: la última unidad
    it = await e.container.inventory_items.get(e.choco)
    it.stock_quantity = 100
    await e.container.inventory_items.update(it)

    async def attempt(cs_index: int, tag: str):
        try:
            o = await create_order(
                deps,
                customer_session_id=e.cs_ids[cs_index],
                table_session_id=e.table_session.id,
                table_id=e.table_id,
                idempotency_key=f"k-race-{tag}",
                lines=sphere(e, choco_balls=1),
            )
            return o.id
        except NotEnoughStockError:
            return None

    results = await asyncio.gather(attempt(0, "a"), attempt(1, "b"))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1, f"debe ganar exactamente un cliente; obtuvo {results}"

    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 100
    assert item.stock_quantity == 100

    orders = await list_orders(deps, table_id=e.table_id)
    assert len(orders) == 1
    assert orders[0].id == winners[0]
    # sin reservas duplicadas ni órdenes parciales
    reservations_db = e.container.client[e.container.db_name]["reservations"]
    assert await reservations_db.count_documents({}) == 1


async def test_concurrency_mixed_quantities(env):
    """Segundo escenario: tres intentos de 100 g simultáneos contra 100 g."""
    e = env
    deps = e.container.orders_deps
    it = await e.container.inventory_items.get(e.choco)
    it.stock_quantity = 100
    await e.container.inventory_items.update(it)

    async def attempt(cs_index: int, balls: int, tag: str):
        try:
            o = await create_order(
                deps,
                customer_session_id=e.cs_ids[cs_index % len(e.cs_ids)],
                table_session_id=e.table_session.id,
                table_id=e.table_id,
                idempotency_key=f"k-mix-{tag}",
                lines=sphere(e, choco_balls=balls),
            )
            return o.id
        except NotEnoughStockError:
            return None

    results = await asyncio.gather(attempt(0, 1, "x"), attempt(1, 1, "y"), attempt(0, 1, "z"))
    winners = [r for r in results if r is not None]
    # 3 intentos × 100 g contra 100 g disponibles ⇒ exactamente 1 ganador
    assert len(winners) == 1
    item = await e.container.inventory_items.get(e.choco)
    assert item.reserved_quantity == 100
    assert item.stock_quantity == 100
