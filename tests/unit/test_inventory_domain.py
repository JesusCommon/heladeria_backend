"""Pruebas unitarias del inventario (invariantes de cantidad)."""

import pydantic
import pytest

from heladeria_backend.inventory.domain.inventory import (
    InventoryItem,
    Reservation,
    ReservationLine,
    ReservationState,
)


def test_available_is_stock_minus_reserved():
    item = InventoryItem(name="Chocolate", unit="g", stock_quantity=1000, reserved_quantity=300)
    assert item.available == 700


def test_reserved_cannot_exceed_stock():
    with pytest.raises(pydantic.ValidationError):
        InventoryItem(name="Chocolate", unit="g", stock_quantity=100, reserved_quantity=400)


def test_negative_quantities_rejected():
    with pytest.raises(pydantic.ValidationError):
        InventoryItem(name="x", unit="g", stock_quantity=-1)


def test_track_stock_false_means_unlimited():
    item = InventoryItem(name="Mermelada", unit="unit", stock_quantity=0, reserved_quantity=0, track_stock=False)
    assert item.available == float("inf")


@pytest.mark.parametrize("status", [ReservationState.CONSUMED, ReservationState.RELEASED, ReservationState.EXPIRED])
def test_reservation_states(status):
    from datetime import timedelta

    r = Reservation(
        order_id="o1",
        lines=[ReservationLine(inventory_item_id="i", quantity=1, unit="g")],
        status=status,
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc) + timedelta(minutes=10),
    )
    assert r.status is status
