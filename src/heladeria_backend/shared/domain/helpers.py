"""SHA-256 helpers para tokens de dispositivos y sesiones."""

import hashlib


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
