"""Inventario vía HTTP: entradas, ajustes, movimientos, reservas (§ 6)."""

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _item(api_env, stock=500, unit="g", name=None):
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        "/api/v1/admin/inventory/items",
        json={"name": name or f"Ingrediente-{uuid.uuid4().hex[:6]}", "unit": unit,
              "stock_quantity": stock, "minimum_stock": 100},
        headers=owner,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_create_item_owner_only(api_env):
    staff = await api_env.staff_headers()
    res = await api_env.http.post(
        "/api/v1/admin/inventory/items",
        json={"name": "x", "unit": "g", "stock_quantity": 10},
        headers=staff,
    )
    assert res.status_code == 403


async def test_entry_and_movements(api_env):
    item = await _item(api_env, stock=0)
    owner = await api_env.owner_headers()
    entry = await api_env.http.post(
        f"/api/v1/admin/inventory/items/{item['id']}/entries",
        json={"quantity": 300, "reason": "compra semanal"},
        headers=owner,
    )
    assert entry.status_code == 200
    assert entry.json()["stock_quantity"] == 300

    moves = await api_env.http.get(
        f"/api/v1/admin/inventory/items/{item['id']}/movements", headers=owner
    )
    types = [m["type"] for m in moves.json()]
    assert "entry" in types
    # trazabilidad: cada movimiento registra motivo y actor
    entry_moves = [m for m in moves.json() if m["type"] == "entry"]
    assert any(m["actor"] and m["reason"] for m in entry_moves)


async def test_invalid_entry_quantity_422(api_env):
    item = await _item(api_env)
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        f"/api/v1/admin/inventory/items/{item['id']}/entries",
        json={"quantity": -5},
        headers=owner,
    )
    assert res.status_code == 422


async def test_adjustment_requires_reason(api_env):
    item = await _item(api_env)
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        f"/api/v1/admin/inventory/items/{item['id']}/adjustments",
        json={"delta": -10, "reason": ""},
        headers=owner,
    )
    assert res.status_code == 422

    ok = await api_env.http.post(
        f"/api/v1/admin/inventory/items/{item['id']}/adjustments",
        json={"delta": -10, "reason": "derrame en cocina"},
        headers=owner,
    )
    assert ok.status_code == 200
    assert ok.json()["stock_quantity"] == item["stock_quantity"] - 10
    moves = await api_env.http.get(
        f"/api/v1/admin/inventory/items/{item['id']}/movements", headers=owner
    )
    assert any(m["type"] == "adjustment" for m in moves.json())


async def test_adjustment_cannot_make_stock_negative(api_env):
    item = await _item(api_env, stock=10)
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        f"/api/v1/admin/inventory/items/{item['id']}/adjustments",
        json={"delta": -50, "reason": "robo"},
        headers=owner,
    )
    assert res.status_code == 422


async def test_low_stock_flag(api_env):
    item = await _item(api_env, stock=50)  # minimum_stock=100
    assert item["low_stock"] is True
    assert item["available_quantity"] == 50
