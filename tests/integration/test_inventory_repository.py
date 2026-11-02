"""Repositorios de inventario y operaciones atómicas (contra Mongo real).

La sesión se propaga explícitamente a cada operación, tal como los
repositorios del dominio deberán hacerlo.
"""

import uuid

import pytest

from heladeria_backend.inventory.domain.inventory import InventoryItem
from heladeria_backend.shared.adapters.outbound.persistence.mongo.unit_of_work import (
    MongoUnitOfWork,
)
from heladeria_backend.shared.domain.errors import (
    NotEnoughStockError,
    NotFoundError,
    UnavailableError,
)

pytestmark = pytest.mark.integration


async def make_item(inventory_repo, name, unit, qty, active=True) -> InventoryItem:
    item = InventoryItem(name=name, unit=unit, stock_quantity=qty, is_active=active)
    await inventory_repo.create(item)
    return item


def oid() -> str:
    return str(uuid.uuid4())


async def test_inventory_item_crud(container):
    repo = container.inventory_items
    item = await make_item(repo, "Chocolate", "g", 1000)
    got = await repo.get(item.id)
    assert got and got.name == "Chocolate" and got.available == 1000

    got.minimum_stock = 200
    await repo.update(got)
    assert (await repo.get(item.id)).minimum_stock == 200

    all_items = await repo.list()
    assert any(i.id == item.id for i in all_items)

    got.is_active = False
    await repo.update(got)
    assert not (await repo.get(item.id)).is_active


def with_uow(container):
    return MongoUnitOfWork(container.client, container.db_name)


async def test_atomic_reserve_release_roundtrip(container):
    ops = container.inv_atomic
    item = await make_item(container.inventory_items, "Chispas", "g", 100)

    async with with_uow(container) as u:
        await ops.reserve({item.id: 10}, oid(), "tester", u.session)

    it = await container.inventory_items.get(item.id)
    assert it.reserved_quantity == 10
    assert it.available == 90

    async with with_uow(container) as u:
        await ops.release({item.id: 10}, oid(), "tester", u.session)

    it = await container.inventory_items.get(item.id)
    assert it.reserved_quantity == 0
    assert it.available == 100

    moves = await container.movements.list_by_item(item.id)
    types = [m.type.value for m in moves]
    assert "reserve" in types and "release" in types


async def test_reserve_insufficient_stock_abort_atomic(container):
    ops = container.inv_atomic
    item = await make_item(container.inventory_items, "Arequipe", "g", 50)
    with pytest.raises(NotEnoughStockError):
        async with with_uow(container) as u:
            await ops.reserve({item.id: 60}, oid(), None, u.session)
    it = await container.inventory_items.get(item.id)
    assert it.reserved_quantity == 0
    assert it.stock_quantity == 50


async def test_reserve_inactive_item_rejected(container):
    ops = container.inv_atomic
    item = await make_item(container.inventory_items, "Vainilla", "g", 500, active=False)
    with pytest.raises(UnavailableError):
        async with with_uow(container) as u:
            await ops.reserve({item.id: 10}, oid(), None, u.session)


async def test_reserve_missing_item_rejected(container):
    ops = container.inv_atomic
    with pytest.raises(NotFoundError):
        async with with_uow(container) as u:
            await ops.reserve({"no-existe": 10}, oid(), None, u.session)


async def test_consume_decrements_stock_and_reserved(container):
    ops = container.inv_atomic
    item = await make_item(container.inventory_items, "Fresa", "g", 200)
    async with with_uow(container) as u:
        await ops.reserve({item.id: 100}, oid(), None, u.session)
    async with with_uow(container) as u:
        await ops.consume({item.id: 100}, oid(), None, u.session)
    it = await container.inventory_items.get(item.id)
    assert it.stock_quantity == 100
    assert it.reserved_quantity == 0


async def test_release_over_reserved_rejected(container):
    ops = container.inv_atomic
    item = await make_item(container.inventory_items, "Pistacho", "g", 100)
    with pytest.raises(Exception):
        async with with_uow(container) as u:
            await ops.release({item.id: 50}, oid(), None, u.session)


async def test_reserve_skips_track_stock_false(container):
    ops = container.inv_atomic
    item = await make_item(container.inventory_items, "Gratis", "unit", 0, active=True)
    item.track_stock = False
    await container.inventory_items.update(item)
    async with with_uow(container) as u:
        await ops.reserve({item.id: 999_999}, oid(), None, u.session)
    it = await container.inventory_items.get(item.id)
    assert it.reserved_quantity == 0
