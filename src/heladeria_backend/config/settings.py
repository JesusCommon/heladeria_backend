from functools import lru_cache
from typing import Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="APP_",
    )

    name: str
    slug: str
    version: str
    timezone: str
    locale: str
    environment: Literal["development", "staging", "production", "testing"]
    debug: bool

class MongoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="MONGODB_",
    )

    url: str
    database: str
    pool_min_size: int = Field(ge=0)
    pool_max_size: int = Field(gt=0)
    server_selection_timeout_ms: int = Field(gt=0)
    connect_timeout_ms: int = Field(gt=0)
    socket_timeout_ms: int = Field(gt=0)
    wait_queue_timeout_ms: int = Field(default=10_000, gt=0)
    max_idle_time_ms: int = Field(default=120_000, gt=0)
    connect_max_attempts: int = Field(default=5, gt=0)
    connect_backoff_ms: int = Field(default=1_000, ge=0)

    @field_validator("url")
    @classmethod
    def _validate_uri(cls, v: str) -> str:
        if not v.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("La URL debe empezar con mongodb:// o mongodb+srv://")
        return v

    @model_validator(mode="after")
    def _check_pool(self) -> "MongoSettings":
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("pool_min_size no puede ser mayor que pool_max_size")
        return self

class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SECURITY_",
    )

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = Field(default=720, gt=0)
    device_link_ttl_minutes: int = Field(default=10, gt=0)

    @field_validator("jwt_secret")
    @classmethod
    def _validate_secret(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("jwt_secret debe tener al menos 16 caracteres")
        return v


class BusinessSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="BUSINESS_",
    )

    # D3: expiración de reservas de pedidos aún no aceptados
    reservation_ttl_seconds: int = Field(default=600, gt=0)
    # D4: vigencia lógica de claves de idempotencia
    idempotency_ttl_seconds: int = Field(default=86400, gt=0)
    # Intervalo del barrido de expiración (tarea en segundo plano)
    expiration_sweep_seconds: int = Field(default=30, gt=0)
    currency: str = "COP"


class AdminSeedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="ADMIN_SEED_",
    )

    enabled: bool = True
    owner_username: str = "owner"
    owner_password: str = "heladeria-owner-123"


class Settings:
    def __init__(self) -> None:
        self.app = AppSettings()
        self.mongo = MongoSettings()
        self.security = SecuritySettings()
        self.business = BusinessSettings()
        self.admin_seed = AdminSeedSettings()

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()