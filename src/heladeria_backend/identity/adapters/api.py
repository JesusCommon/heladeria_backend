"""API de autenticación administrativa."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from heladeria_backend.identity.adapters.api_security import (
    container,
    get_admin_principal,
)
from heladeria_backend.identity.application.use_cases import (
    create_user,
    login,
)
from heladeria_backend.identity.domain.identity import Principal, Role
from heladeria_backend.shared.adapters.inbound.http.rate_limit import (
    FailedAttemptLimiter,
    assert_allowed,
    client_ip,
)
from heladeria_backend.shared.domain.errors import DomainError

router = APIRouter(prefix="/admin", tags=["admin-auth"])


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class CreateUserInput(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{3,32}$")
    password: str = Field(min_length=10)
    role: Role = Role.STAFF


# Límites de fuerza bruta: fallos por ventana (por IP y por IP+usuario).
_LOGIN_IP_LIMIT = FailedAttemptLimiter(max_attempts=30, window_seconds=60)
_LOGIN_USER_LIMIT = FailedAttemptLimiter(max_attempts=10, window_seconds=60)


@router.post("/auth/login")
async def admin_login(dto: LoginInput, request: Request):
    ip = client_ip(request)
    ip_key = f"login:{ip}"
    user_key = f"{ip_key}:user:{dto.username}"
    assert_allowed(_LOGIN_IP_LIMIT, ip_key)
    assert_allowed(_LOGIN_USER_LIMIT, user_key)
    c = container(request)
    try:
        user, token = await login(c.identity, dto.username, dto.password)
    except DomainError:
        _LOGIN_IP_LIMIT.record(ip_key)
        _LOGIN_USER_LIMIT.record(user_key)
        raise HTTPException(401, "Credenciales inválidas")
    _LOGIN_IP_LIMIT.reset(ip_key)
    _LOGIN_USER_LIMIT.reset(user_key)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "role": user.role.value},
    }


@router.post("/users", status_code=201)
async def admin_create_user(
    dto: CreateUserInput,
    request: Request,
    principal: Annotated[Principal, Depends(get_admin_principal)],
) -> dict:
    c = container(request)
    user = await create_user(c.identity, principal, dto.username, dto.password, dto.role)
    return {"id": user.id, "username": user.username, "role": user.role.value}
