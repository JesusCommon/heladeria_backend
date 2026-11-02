"""Errores de dominio compartidos.

Cada error declara su `status_code` HTTP para mapear limpiamente en la API
sin que el dominio conozca HTTP.
"""

Status = int


class DomainError(Exception):
    status_code: Status = 500
    code: str = "domain_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DomainValidationError(DomainError):
    status_code = 422
    code = "validation_error"


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class NotEnoughStockError(ConflictError):
    status_code = 409
    code = "not_enough_stock"


class AuthError(DomainError):
    status_code = 401
    code = "auth_error"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


class UnavailableError(DomainError):
    status_code = 422
    code = "unavailable"
