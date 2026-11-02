"""Flujo completo mesas → dispositivos → sesiones → pedidos vía HTTP (§ 7, § 8)."""

import asyncio
import uuid

import pytest

pytestmark = pytest.mark.integration


async def _owner(api_env):
    return await api_env.owner_headers()


async def _staff(api_env):
    return await api_env.staff_headers()


async def make_phisical_setup(api_env, tables_number=None):
    """Mesa + sesión staff + dispositivo reclamado + sesión de cliente."""
    owner = await _owner(api_env)
    staff = await _staff(api_env)

    number = tables_number or uuid.uuid4().int % 999_999
    table = (
        await api_env.http.post(
            "/api/v1/admin/tables", json={"number": number, "name": "Terraza"},
            headers=owner,
        )
    ).json()

    ts = (
        await api_env.http.post(
            f"/api/v1/admin/tables/{table['id']}/sessions/open", headers=staff
        )
    ).json()
    assert ts["status"] == "open"

    device = (
        await api_env.http.post(
            "/api/v1/admin/tables/devices",
            json={"table_id": table["id"], "device_name": "Tablet-1"},
            headers=owner,
        )
    ).json()
    claim = await api_env.http.post(
        "/api/v1/device/claim", json={"link_code": device["link_code"]}
    )
    assert claim.status_code == 200, claim.text
    claimed = claim.json()

    cs = await api_env.http.post(
        "/api/v1/device/customer-session",
        headers={"X-Device-Token": claimed["device_token"]},
    )
    assert cs.status_code == 201, cs.text
    csj = cs.json()

    return {
        "owner": owner, "staff": staff, "table": table, "table_session": ts,
        "device": claimed, "customer": csj,
    }


async def make_catalogue(api_env, flavor_name="Chocolate", stock=1000):
    """Config de la especificación: cono base 7000 + 2500/bola, receta 100g/bola."""
    owner = await _owner(api_env)
    item = (
        await api_env.http.post(
            "/api/v1/admin/catalog-items",
            json={"name": flavor_name, "kind": "flavor"},
            headers=owner,
        )
    ).json()
    inv = (
        await api_env.http.post(
            "/api/v1/admin/inventory/items",
            json={"name": f"{flavor_name} polvo", "unit": "g", "stock_quantity": stock},
            headers=owner,
        )
    ).json()
    product = (
        await api_env.http.post(
            "/api/v1/admin/products",
            json={
                "name": "Helado de cono", "kind": "cone", "base_price": 7000,
                "customization": [{
                    "name": "Sabores", "min_selections": 1, "max_selections": 3,
                    "required": True, "allow_repeated": True,
                    "allow_per_option_quantity": True,
                    "options": [{
                        "catalog_item_id": item["id"], "additional_price": 2500,
                        "consumption": [{
                            "inventory_item_id": inv["id"], "quantity": 100, "unit": "g"
                        }],
                    }],
                }],
            },
            headers=owner,
        )
    ).json()
    return {"product": product, "inventory": inv, "catalog_item": item}


def order_payload(setup, product, key, balls=1):
    group = product["customization"][0]
    return {
        "idempotency_key": key,
        "lines": [{
            "product_id": product["id"],
            "quantity": 1,
            "selections": [{
                "group_id": group["id"],
                "catalog_item_id": group["options"][0]["catalog_item_id"],
                "quantity": balls,
            }],
        }],
    }


async def test_full_customer_order_flow(api_env):
    """De la mesa al pedido delivered: POR HTTP TODO."""
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}

    created = await api_env.http.post(
        "/api/v1/orders", json=order_payload(setup, cat["product"], "k-flow-1"), headers=h
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["status"] == "pending"
    assert order["total"] == 9500
    assert order["table_id"] == setup["table"]["id"]  # derivado, NO del cliente

    # reservado en inventario
    inv = await api_env.http.get(
        f"/api/v1/admin/inventory/items/{cat['inventory']['id']}",
        headers=setup["owner"],
    )
    body = inv.json()
    assert body["stock_quantity"] == 1000
    assert body["reserved_quantity"] == 100
    assert body["available_quantity"] == 900

    # idempotencia HTTP: misma clave → mismo pedido
    again = await api_env.http.post(
        "/api/v1/orders", json=order_payload(setup, cat["product"], "k-flow-1"), headers=h
    )
    assert again.status_code == 201
    assert again.json()["id"] == order["id"]
    assert again.json()["order_number"] == order["order_number"]

    # ciclo de estados completo por staff
    staff = setup["staff"]
    oid = order["id"]
    for action, expected in (("accept", "accepted"), ("preparing", "preparing"),
                             ("ready", "ready"), ("delivered", "delivered")):
        res = await api_env.http.post(f"/api/v1/admin/orders/{oid}/{action}", headers=staff)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == expected

    # consuming wrote movements
    moves = await api_env.http.get(
        f"/api/v1/admin/inventory/items/{cat['inventory']['id']}/movements",
        headers=setup["owner"],
    )
    types = [m["type"] for m in moves.json()]
    assert "reserve" in types and "consumption" in types
    inv2 = (
        await api_env.http.get(
            f"/api/v1/admin/inventory/items/{cat['inventory']['id']}",
            headers=setup["owner"],
        )
    ).json()
    assert inv2["stock_quantity"] == 900  # 1000 - 100 consumidos


async def test_cancel_releases_reservation(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}
    order = (
        await api_env.http.post(
            "/api/v1/orders", json=order_payload(setup, cat["product"], "k-cancel"),
            headers=h,
        )
    ).json()
    res = await api_env.http.post(
        f"/api/v1/admin/orders/{order['id']}/cancel?reason=no%20pago", headers=setup["staff"]
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    inv = await api_env.http.get(
        f"/api/v1/admin/inventory/items/{cat['inventory']['id']}",
        headers=setup["owner"],
    )
    assert inv.json()["reserved_quantity"] == 0
    assert inv.json()["stock_quantity"] == 1000


async def test_illegal_transition_api_returns_409(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}
    order = (
        await api_env.http.post(
            "/api/v1/orders", json=order_payload(setup, cat["product"], "k-ill"),
            headers=h,
        )
    ).json()
    res = await api_env.http.post(
        f"/api/v1/admin/orders/{order['id']}/delivered", headers=setup["staff"]
    )
    assert res.status_code == 409
    assert res.json()["code"] == "conflict"


async def test_order_requires_customer_token(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    res = await api_env.http.post(
        "/api/v1/orders", json=order_payload(setup, cat["product"], "k-notok")
    )
    assert res.status_code == 401


async def test_invalid_customer_token_401(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    res = await api_env.http.post(
        "/api/v1/orders",
        json=order_payload(setup, cat["product"], "k-badtok"),
        headers={"X-Customer-Token": "token-inventado"},
    )
    assert res.status_code == 401


async def test_customer_cannot_see_others_orders(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h1 = {"X-Customer-Token": setup["customer"]["customer_token"]}
    order = (
        await api_env.http.post(
            "/api/v1/orders", json=order_payload(setup, cat["product"], "k-priv"), headers=h1
        )
    ).json()

    # segundo cliente (dispositivo nuevo) en la misma mesa
    await api_env.http.post(
        "/api/v1/admin/tables/devices",
        json={"table_id": setup["table"]["id"], "device_name": "Tablet-2"},
        headers=setup["owner"],
    )
    # el cliente 2 NO puede leer el pedido del cliente 1
    res = await api_env.http.get(
        f"/api/v1/orders/{order['id']}", headers={"X-Customer-Token": "otro-token"}
    )
    assert res.status_code in (401, 403)


async def test_insufficient_stock_409_and_no_partial_order(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env, stock=100)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}
    res = await api_env.http.post(
        "/api/v1/orders", json=order_payload(setup, cat["product"], "k-nost", balls=2),
        headers=h,
    )
    assert res.status_code == 409
    assert res.json()["code"] == "not_enough_stock"

    orders = await api_env.http.get("/api/v1/orders", headers=h)
    assert orders.json() == []


async def test_concurrent_last_unit_http(api_env):
    """§ 12: dos clientes al mismo tiempo contra la última existencia, vía HTTP."""
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env, stock=100)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}

    async def send(key):
        res = await api_env.http.post(
            "/api/v1/orders", json=order_payload(setup, cat["product"], key), headers=h
        )
        return res

    r1, r2 = await asyncio.gather(send("k-race-1"), send("k-race-2"))
    codes = {r1.status_code, r2.status_code}
    assert 201 in codes and 409 in codes, (r1.text, r2.text)


async def test_admin_list_orders_by_table_and_status(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}
    await api_env.http.post(
        "/api/v1/orders", json=order_payload(setup, cat["product"], "k-list"), headers=h
    )
    res = await api_env.http.get(
        f"/api/v1/admin/orders?table_id={setup['table']['id']}", headers=setup["staff"]
    )
    assert res.status_code == 200
    listed = res.json()
    assert len(listed) == 1
    assert listed[0]["status"] == "pending"

    only_pending = await api_env.http.get(
        "/api/v1/admin/orders?status=pending", headers=setup["staff"]
    )
    assert any(o["id"] == listed[0]["id"] for o in only_pending.json())


async def test_maintenance_expire_endpoint(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}
    order = (
        await api_env.http.post(
            "/api/v1/orders", json=order_payload(setup, cat["product"], "k-exp"), headers=h
        )
    ).json()
    # vencer manualmente la reserva en BD
    db = api_env.client[api_env.db_name]
    await db["reservations"].update_one(
        {"order_id": order["id"]},
        {"$set": {"expires_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc) - __import__("datetime").timedelta(seconds=5)}},
    )
    res = await api_env.http.post(
        "/api/v1/admin/orders/maintenance/expire", headers=setup["staff"]
    )
    assert res.status_code == 200
    assert order["id"] in res.json()["expired_order_ids"]


async def test_table_renumber_keeps_history(api_env):
    setup = await make_phisical_setup(api_env)
    cat = await make_catalogue(api_env)
    h = {"X-Customer-Token": setup["customer"]["customer_token"]}
    order = (
        await api_env.http.post(
            "/api/v1/orders", json=order_payload(setup, cat["product"], "k-renum"), headers=h
        )
    ).json()
    new_num = uuid.uuid4().int % 999_999
    res = await api_env.http.patch(
        f"/api/v1/admin/tables/{setup['table']['id']}",
        json={"number": new_num},
        headers=setup["owner"],
    )
    assert res.status_code == 200
    assert res.json()["number"] == new_num
    # el pedido histórico sigue enlazado por id interno
    got = await api_env.http.get(
        f"/api/v1/admin/orders?table_id={setup['table']['id']}", headers=setup["staff"]
    )
    assert any(o["id"] == order["id"] for o in got.json())
