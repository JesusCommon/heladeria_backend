"""Fixtures de la suite de API: app FastAPI completa contra Mongo real (rs0)."""

import uuid

import httpx
import pytest_asyncio

from heladeria_backend.bootstrap.app_factory import create_app
from heladeria_backend.bootstrap.container import build_container
from heladeria_backend.bootstrap.indexes import ensure_indexes
from heladeria_backend.config.settings import settings
from heladeria_backend.identity.application.use_cases import seed_owner_if_empty


class _StubConnection:
    connected = True


@pytest_asyncio.fixture
async def api_env():
    from heladeria_backend.shared.adapters.outbound.persistence.mongo import (
        create_mongo_client,
    )

    client = create_mongo_client()
    db_name = f"heladeria_api_{uuid.uuid4().hex[:8]}"
    await ensure_indexes(client, db_name)
    container = build_container(client, database_name=db_name)

    app = create_app()
    app.state.container = container
    app.state.mongo_connection = _StubConnection()

    # seed OWNER (sin lifespan)
    await seed_owner_if_empty(
        container.identity,
        settings.admin_seed.owner_username,
        settings.admin_seed.owner_password,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield Env(
            container=container, db_name=db_name, client=client, http=http, app=app
        )

    await client.drop_database(db_name)
    await client.close()


class Env:
    def __init__(self, container, db_name, client, http, app):
        self.container = container
        self.db_name = db_name
        self.client = client
        self.http = http
        self.app = app
        self._owner_headers: dict | None = None
        self._staff_headers: dict | None = None

    async def owner_headers(self) -> dict:
        if self._owner_headers is None:
            self._owner_headers = await self.login(
                settings.admin_seed.owner_username, settings.admin_seed.owner_password
            )
        return self._owner_headers

    async def staff_headers(self) -> dict:
        if self._staff_headers is None:
            # OWNER crea un STAFF con login propio
            await self.http.post(
                "/api/v1/admin/users",
                json={"username": "staffer", "password": "staff-password-123", "role": "staff"},
                headers=await self.owner_headers(),
            )
            self._staff_headers = await self.login("staffer", "staff-password-123")
        return self._staff_headers

    async def login(self, username, password) -> dict:
        res = await self.http.post(
            "/api/v1/admin/auth/login", json={"username": username, "password": password}
        )
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}
