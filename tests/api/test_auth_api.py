"""Autenticación, autorización y manejo de errores HTTP (§ 9 y § 10)."""

import pytest

pytestmark = pytest.mark.integration


async def test_login_ok_and_me_flow(api_env):
    res = await api_env.http.post(
        "/api/v1/admin/auth/login",
        json={"username": "owner", "password": "heladeria-owner-123"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "owner"
    assert "access_token" in body


async def test_login_wrong_password_401(api_env):
    res = await api_env.http.post(
        "/api/v1/admin/auth/login",
        json={"username": "owner", "password": "wrong-password"},
    )
    assert res.status_code == 401
    assert "credenciales" in res.json()["detail"].lower()


async def test_unknown_user_401(api_env):
    res = await api_env.http.post(
        "/api/v1/admin/auth/login", json={"username": "ghost", "password": "x"}
    )
    assert res.status_code == 401


async def test_admin_endpoint_requires_token(api_env):
    res = await api_env.http.get("/api/v1/admin/products")
    assert res.status_code == 401


async def test_invalid_token_401(api_env):
    res = await api_env.http.get(
        "/api/v1/admin/products", headers={"Authorization": "Bearer no-es-un-jwt"}
    )
    assert res.status_code == 401


async def test_owner_only_endpoints_reject_staff(api_env):
    """STAFF no puede crear/gestionar catálogo (mínimo privilegio)."""
    staff = await api_env.staff_headers()
    res = await api_env.http.post(
        "/api/v1/admin/products",
        json={"name": "x", "base_price": 100},
        headers=staff,
    )
    assert res.status_code == 403


async def test_staff_can_read_admin_listings(api_env):
    staff = await api_env.staff_headers()
    res = await api_env.http.get("/api/v1/admin/products", headers=staff)
    assert res.status_code == 200
    assert res.json() == []


async def test_owner_creates_staff_user(api_env):
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        "/api/v1/admin/users",
        json={"username": "nuevo", "password": "muy-segura-123", "role": "staff"},
        headers=owner,
    )
    assert res.status_code == 201
    assert res.json()["role"] == "staff"
    # login del nuevo usuario
    res2 = await api_env.http.post(
        "/api/v1/admin/auth/login",
        json={"username": "nuevo", "password": "muy-segura-123"},
    )
    assert res2.status_code == 200


async def test_short_password_rejected(api_env):
    owner = await api_env.owner_headers()
    res = await api_env.http.post(
        "/api/v1/admin/users",
        json={"username": "corto", "password": "123", "role": "staff"},
        headers=owner,
    )
    assert res.status_code == 422


async def test_admin_isolated_from_device_sessions(api_env):
    """Un token de dispositivo/sesión de cliente JAMÁS autentica como admin."""
    res = await api_env.http.get(
        "/api/v1/admin/products", headers={"Authorization": "Bearer cus-token-falso"}
    )
    assert res.status_code == 401
