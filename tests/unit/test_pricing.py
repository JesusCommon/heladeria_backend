"""Pruebas unitarias del servicio de precios (Decisión D1)."""

import pytest

from heladeria_backend.catalog.domain.catalog import SelectionInput
from heladeria_backend.pricing.domain.service import order_total, price_line

from .fixtures_catalog import cone_product, flavor_id

CHOCO = flavor_id()
VANI = flavor_id()


def test_base_price_only():
    p = cone_product([CHOCO, VANI])
    g = p.customization[0]
    price = price_line(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1)], 1)
    assert price.base_price == 7000
    assert price.options_price == 2500
    assert price.unit_final_price == 9500
    assert price.subtotal == 9500


def test_optionals_and_quantity():
    p = cone_product([CHOCO, VANI])
    sabor, salsa, deco = p.customization
    sels = [
        SelectionInput(group_id=sabor.id, catalog_item_id=CHOCO, quantity=2),
        SelectionInput(group_id=sabor.id, catalog_item_id=VANI, quantity=1),
        SelectionInput(group_id=salsa.id, catalog_item_id="salsa-1", quantity=1),
    ]
    price = price_line(p, sels, 1)
    # base 7000 + 3×2500 sabores + 1000 salsa
    assert price.unit_final_price == 7000 + 7500 + 1000
    assert price.subtotal == price.unit_final_price


def test_line_quantity_multiplies_subtotal():
    p = cone_product([CHOCO])
    g = p.customization[0]
    price = price_line(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1)], 3)
    assert price.quantity == 3
    assert price.subtotal == price.unit_final_price * 3


def test_order_total():
    p = cone_product([CHOCO])
    g = p.customization[0]
    a = price_line(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1)], 1)
    b = price_line(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1)], 2)
    assert order_total([a, b]) == a.subtotal + b.subtotal


def test_client_sent_prices_are_ignored():
    """El precio NUNCA sale de la entrada del cliente (§ 6 integridad):
    `price_line` solo lee del catálogo; no acepta parámetro de precio."""
    p = cone_product([CHOCO])
    g = p.customization[0]
    price = price_line(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1)], 1)
    # un atacante no puede inyectar valores; la función ni siquiera expone el campo
    assert all(s.unit_price == p.customization[0].options[0].additional_price for s in price.selections)


def test_snapshots_preserve_names_and_prices():
    p = cone_product([CHOCO])
    g = p.customization[0]
    price = price_line(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=2)], 1)
    snap = price.selections[0]
    assert snap.catalog_item_id == CHOCO
    assert snap.quantity == 2
    assert snap.unit_price == 2500
    assert snap.group_name == "Sabores"


def test_negative_base_price_rejected():
    import pydantic

    from heladeria_backend.catalog.domain.catalog import Product

    with pytest.raises(pydantic.ValidationError):
        Product(name="x", base_price=-5)
