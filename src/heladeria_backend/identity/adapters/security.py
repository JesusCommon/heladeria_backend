"""Adaptadores de seguridad: Argon2id y JWT (PyJWT HS256)."""

from datetime import UTC, datetime, timedelta

import argon2
import jwt

from heladeria_backend.config.settings import settings
from heladeria_backend.identity.domain.identity import Principal, Role
from heladeria_backend.identity.domain.ports import PasswordHasher, TokenIssuer
from heladeria_backend.shared.domain.errors import AuthError


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._hasher = argon2.PasswordHasher()

    def hash(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            self._hasher.verify(hashed, plain)
            return True
        except argon2.exceptions.Argon2Error:
            return False


class JwtTokenService(TokenIssuer):
    def issue(self, principal: Principal) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": principal.sub,
            "role": principal.role.value,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=settings.security.jwt_ttl_minutes)).timestamp()),
        }
        return jwt.encode(
            claims, settings.security.jwt_secret,
            algorithm=settings.security.jwt_algorithm,
        )

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token, settings.security.jwt_secret,
                algorithms=[settings.security.jwt_algorithm],
            )
        except jwt.PyJWTError as e:
            raise AuthError(f"Token inválido: {e}")
        try:
            return Principal(
                sub=claims["sub"],
                role=Role(claims["role"]),
                exp=datetime.fromtimestamp(claims["exp"], tz=UTC),
            )
        except KeyError as e:
            raise AuthError(f"Token sin claims: {e}")
