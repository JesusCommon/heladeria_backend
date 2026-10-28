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

class Settings:
    def __init__(self) -> None:
        self.app = AppSettings()
        self.mongo = MongoSettings()

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()