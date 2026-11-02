"""Dependencias de autenticación HTTP (token admin / sesión de cliente)."""

from typing import Annotated

from fastapi import Depends, Header, Request

from heladeria_backend.bootstrap.container import Container
from heladeria_backend.identity.adapters.security import JwtTokenService
from heladeria_backend.identity.domain.identity import Principal, Role
from heladeria_backend.shared.domain.errors import AuthError
from heladeria_backend.shared.domain.helpers import sha256_hex


def container(request: Request) -> Container:
    return request.app.state.container


def get_admin_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Falta el token de administrador")
    token = authorization[len("Bearer "):]
    svc = JwtTokenService()
    return svc.verify(token)


def require_owner(principal: Annotated[Principal, Depends(get_admin_principal)]) -> Principal:
    from heladeria_backend.shared.domain.errors import PermissionDeniedError

    if principal.role != Role.OWNER:
        raise PermissionDeniedError("Se requiere rol OWNER")
    return principal


def require_staff(principal: Annotated[Principal, Depends(get_admin_principal)]) -> Principal:
    return principal  # OWNER o STAFF


async def get_customer_session(
    request: Request,
    x_customer_token: Annotated[str | None, Header()] = None,
):
    from heladeria_backend.tables.domain.ports import CustomerSessionRepository

    if not x_customer_token:
        raise AuthError("Falta X-Customer-Token de sesión de cliente")
    repo: CustomerSessionRepository = container(request).tables_ctx.customer_sessions
    cs = await repo.get_by_token_hash(sha256_hex(x_customer_token))
    if cs is None or cs.status != "open":
        raise AuthError("Sesión de cliente inválida o cerrada")
    return cs
