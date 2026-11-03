"""Casos de uso de Identity: login, creación de usuarios y seed."""

from dataclasses import dataclass

import argon2
import structlog

from heladeria_backend.identity.domain.identity import AdminUser, Principal, Role
from heladeria_backend.identity.domain.ports import (
    AdminUserRepository,
    PasswordHasher,
    TokenIssuer,
)
from heladeria_backend.shared.domain.errors import (
    AuthError,
    DomainValidationError,
    PermissionDeniedError,
)

logger = structlog.get_logger()

# Hash ficticio: se verifica un hash Argon2 real aunque el usuario NO exista,
# igualando el tiempo de respuesta y frustrando la enumeración de usuarios
# mediante análisis de timing.
_DUMMY_HASHER = argon2.PasswordHasher()
_DUMMY_HASH = _DUMMY_HASHER.hash("timing-equalizer-not-a-real-password")


class Argon2TimingProbe:
    """Verifica contra el hash dummy: siempre falla, pero con el mismo coste."""

    @staticmethod
    def verify(plain: str) -> None:
        try:
            _DUMMY_HASHER.verify(_DUMMY_HASH, plain)
        except argon2.exceptions.Argon2Error:
            pass


@dataclass
class IdentityContext:
    users: AdminUserRepository
    hasher: PasswordHasher
    tokens: TokenIssuer


async def login(ctx: IdentityContext, username: str, password: str) -> tuple[AdminUser, str]:
    user = await ctx.users.get_by_username(username)
    if user is None or not user.is_active:
        # igualar el timing: gastar el mismo trabajo que una verificación real
        Argon2TimingProbe.verify(password)
        raise AuthError("Credenciales inválidas")
    if not ctx.hasher.verify(password, user.password_hash):
        raise AuthError("Credenciales inválidas")
    principal = Principal(sub=user.id, role=user.role, exp=__never())
    return user, ctx.tokens.issue(principal)


def __never():
    from datetime import UTC, datetime, timedelta
    return datetime.now(UTC) + timedelta(minutes=1)


async def create_user(
    ctx: IdentityContext,
    actor: Principal,
    username: str,
    password: str,
    role: Role,
) -> AdminUser:
    if actor.role != Role.OWNER:
        raise PermissionDeniedError("Solo el OWNER puede crear usuarios administrativos")
    if len(password) < 10:
        raise DomainValidationError("Contraseña mínimo 10 caracteres")
    if role not in {Role.OWNER, Role.STAFF}:
        raise DomainValidationError("Rol inválido")
    if await ctx.users.get_by_username(username) is not None:
        raise DomainValidationError(f"Usuario '{username}' ya existe")
    user = AdminUser(
        username=username,
        password_hash=ctx.hasher.hash(password),
        role=role,
    )
    await ctx.users.save(user)
    logger.info("identity.user.created", username=username, role=role.value)
    return user


async def seed_owner_if_empty(ctx: IdentityContext, username: str, password: str) -> AdminUser | None:
    """Bootstrap de arranque: crea el único OWNER inicial si no hay ningún usuario."""
    if await ctx.users.exists_any():
        return None
    user = AdminUser(username=username, password_hash=ctx.hasher.hash(password), role=Role.OWNER)
    await ctx.users.save(user)
    logger.info("identity.seed.owner", username=username)
    return user
