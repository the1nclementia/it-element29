from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    postgres_host: str = Field(default="localhost", min_length=1)
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="element29", min_length=1)
    postgres_user: str = Field(default="element29", min_length=1)
    postgres_password: SecretStr
    db_connect_timeout: int = Field(default=3, ge=1, le=10)
    enable_api_docs: bool = False
    environment: Literal["development", "production"] = "development"
    cookie_secure: bool = False
    app_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    session_hours: int = Field(default=8, ge=1, le=24)
    login_limit: int = Field(default=5, ge=1, le=100)
    login_ip_limit: int = Field(default=60, ge=1, le=1000)
    login_window_seconds: int = Field(default=900, ge=60, le=3600)
    app_db_user: str = "element29_app"
    app_db_password: SecretStr | None = None
    uploads_dir: Path = Path("/app/uploads")
    photo_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1, le=5 * 1024 * 1024)
    photo_max_pixels: int = Field(default=20_000_000, ge=1, le=20_000_000)
    photo_max_per_item: int = Field(default=5, ge=1, le=5)

    @field_validator("app_origins")
    @classmethod
    def valid_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("APP_ORIGINS must not be empty")
        for origin in origins:
            parts = urlsplit(origin)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.path
                or parts.query
                or parts.fragment
                or "*" in origin
            ):
                raise ValueError("APP_ORIGINS must contain exact HTTP(S) origins without paths")
        return origins

    @model_validator(mode="after")
    def production_requires_secure_cookies(self):
        if self.environment == "production" and (
            not self.cookie_secure or any(not o.startswith("https://") for o in self.app_origins)
        ):
            raise ValueError("Production requires COOKIE_SECURE=true and HTTPS APP_ORIGINS")
        return self

    @field_validator("postgres_password")
    @classmethod
    def password_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("POSTGRES_PASSWORD must not be empty")
        return value

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
