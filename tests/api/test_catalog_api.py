"""Catálogo, personalización y precios vía HTTP (§ 4 y § 5)."""

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _item(api_env, name, kind="flavor"):
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        "/api/v1/admin/catalog-items",
        json={"name": name, "kind": kind},
        headers=owner,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _cone(api_env, flavor_ids, max_balls=3):
    owner = await api_env.owner_headers()
    group = {
        "name": "Sabores",
        "min_selections": 1,
        "max_selections": max_balls,
        "required": True,
        "allow_repeated": True,
        "allow_per_option_quantity": True,
        "options": [
            {"catalog_item_id": fid, "additional_price": 2500} for fid in flavor_ids
        ],
    }
    res = await api_env.http.post(
        "/api/v1/admin/products",
        json={"name": "Helado de cono", "kind": "cone", "base_price": 7000,
              "customization": [group]},
        headers=owner,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_create_and_update_product(api_env):
    f1 = await _item(api_env, "Chocolate")
    p = await _cone(api_env, [f1["id"]])
    assert p["base_price"] == 7000
    assert p["customization"][0]["options"][0]["additional_price"] == 2500

    owner = await api_env.owner_headers()
    upd = await api_env.http.put(
        f"/api/v1/admin/products/{p['id']}",
        json={"name": "Helado de cono XL", "kind": "cone", "base_price": 9000,
              "customization": p["customization"], "is_active": True},
        headers=owner,
    )
    assert upd.status_code == 200
    assert upd.json()["base_price"] == 9000
    assert upd.json()["name"] == "Helado de cono XL"


async def test_cone_max_3_cup_max_4_coexist_per_product(api_env):
    """Reglas independientes por producto sin tocar código."""
    f1 = await _item(api_env, "Fresa")
    cone = await _cone(api_env, [f1["id"]], max_balls=3)
    cup = await _cone(api_env, [f1["id"]], max_balls=4)
    assert cone["customization"][0]["max_selections"] == 3
    assert cup["customization"][0]["max_selections"] == 4


async def test_group_min_over_max_rejected(api_env):
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        "/api/v1/admin/products",
        json={"name": "inválido", "base_price": 100, "customization": [
            {"name": "g", "min_selections": 4, "max_selections": 2, "options": []}
        ]},
        headers=owner,
    )
    assert res.status_code == 422


async def test_duplicate_option_in_group_rejected(api_env):
    f1 = await _item(api_env, "Doble")
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        "/api/v1/admin/products",
        json={"name": "x", "base_price": 100, "customization": [
            {"name": "g", "min_selections": 1, "max_selections": 3, "options": [
                {"catalog_item_id": f1["id"]}, {"catalog_item_id": f1["id"]}
            ]}
        ]},
        headers=owner,
    )
    assert res.status_code == 422


async def test_deactivate_product(api_env):
    f1 = await _item(api_env, "Limon")
    p = await _cone(api_env, [f1["id"]])
    owner = await api_env.owner_headers()
    res = await api_env.http.delete(f"/api/v1/admin/products/{p['id']}", headers=owner)
    assert res.status_code == 204
    got = await api_env.http.get(f"/api/v1/admin/products/{p['id']}", headers=owner)
    assert got.json()["is_active"] is False


async def test_public_catalog_marks_selectability(api_env):
    f1 = await _item(api_env, "Chicle")
    p = await _cone(api_env, [f1["id"]])
    res = await api_env.http.get("/api/v1/public/catalog")
    assert res.status_code == 200
    pub = res.json()
    assert isinstance(pub, list)
    mine = next(x for x in pub if x["id"] == p["id"])
    assert mine["is_selectable"] is True
    assert mine["groups"][0]["options"][0]["is_selectable"] is True
    # NUNCA revela datos de costo interno, solo COP
    assert mine["currency"] == "COP"


async def test_public_catalog_excludes_inactive(api_env):
    f1 = await _item(api_env, "Oculto")
    p = await _cone(api_env, [f1["id"]])
    owner = await api_env.owner_headers()
    await api_env.http.delete(f"/api/v1/admin/products/{p['id']}", headers=owner)
    res = await api_env.http.get("/api/v1/public/catalog")
    ids = [x["id"] for x in res.json()]
    assert p["id"] not in ids


async def _quote(api_env, product, balls=1):
    group = product["customization"][0]
    return await api_env.http.post(
        "/api/v1/public/price-quote",
        json={
            "product_id": product["id"],
            "quantity": 1,
            "selections": [
                {"group_id": group["id"],
                 "catalog_item_id": group["options"][0]["catalog_item_id"],
                 "quantity": balls}
            ],
        },
    )


async def test_price_quote_computed_server_side(api_env):
    f1 = await _item(api_env, "Mora")
    p = await _cone(api_env, [f1["id"]])
    res = await _quote(api_env, p)
    assert res.status_code == 200
    q = res.json()
    assert q["base_price"] == 7000
    assert q["options_price"] == 2500
    assert q["unit_final_price"] == 9500
    assert q["subtotal"] == 9500
    assert q["currency"] == "COP"


async def test_price_quote_quantity_line_subtotal(api_env):
    f1 = await _item(api_env, "Nata")
    p = await _cone(api_env, [f1["id"]])
    owner = await api_env.owner_headers()
    # cotización con quantity=3 del producto
    group = p["customization"][0]
    res = await api_env.http.post(
        "/api/v1/public/price-quote",
        json={
            "product_id": p["id"],
            "quantity": 3,
            "selections": [
                {"group_id": group["id"],
                 "catalog_item_id": group["options"][0]["catalog_item_id"],
                 "quantity": 1}
            ],
        },
    )
    assert res.json()["subtotal"] == 9500 * 3


async def test_price_quote_rejects_tampering(api_env):
    """No hay forma de pasar precios desde el cliente y más bolas se validan."""
    f1 = await _item(api_env, "Pistacho")
    p = await _cone(api_env, [f1["id"]], max_balls=3)
    owner = await api_env.owner_headers()
    group = p["customization"][0]
    # 4 bolas en un cono de 3: rechazo
    res = await api_env.http.post(
        "/api/v1/public/price-quote",
        json={"product_id": p["id"], "quantity": 1,
              "selections": [{"group_id": group["id"],
                              "catalog_item_id": group["options"][0]["catalog_item_id"],
                              "quantity": 4}]},
    )
    assert res.status_code == 422
    # precio malicioso: cualquier campo extra es ignorado
    res2 = await api_env.http.post(
        "/api/v1/public/price-quote",
        json={"product_id": p["id"], "quantity": 1, "base_price": 1, "total": 1,
              "unit_price": 1,
              "selections": [{"group_id": group["id"],
                              "catalog_item_id": group["options"][0]["catalog_item_id"],
                              "quantity": 1, "unit_price": 1}]},
    )
    assert res2.status_code == 200
    assert res2.json()["unit_final_price"] == 9500


async def test_price_quote_unknown_group_422(api_env):
    f1 = await _item(api_env, "Café")
    p = await _cone(api_env, [f1["id"]])
    res = await api_env.http.post(
        "/api/v1/public/price-quote",
        json={"product_id": p["id"], "quantity": 1,
              "selections": [{"group_id": str(uuid.uuid4()),
                              "catalog_item_id": f1["id"], "quantity": 1}]},
    )
    assert res.status_code == 422
