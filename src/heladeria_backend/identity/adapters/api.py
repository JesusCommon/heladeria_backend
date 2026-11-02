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
from heladeria_backend.shared.domain.errors import DomainError

router = APIRouter(prefix="/admin", tags=["admin-auth"])


class LoginInput(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class CreateUserInput(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=10)
    role: Role = Role.STAFF


@router.post("/auth/login")
async def admin_login(dto: LoginInput, request: Request):
    c = container(request)
    try:
        user, token = await login(c.identity, dto.username, dto.password)
    except DomainError:
        raise HTTPException(401, "Credenciales inválidas")
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
