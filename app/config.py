"""Application configuration."""

import json
from functools import lru_cache
from typing import Annotated, Any, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Jira Analytics"
    app_version: str = "1.4.0"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite:///./data/jira_analytics.db"

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Jira Cloud credentials
    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    
    # Sync settings
    jira_request_delay: float = 0.1  # 100ms between requests
    jira_max_retries: int = 3
    jira_batch_size: int = 100  # Issues per request

    # Auth
    jwt_secret_key: Optional[str] = None
    jwt_expire_hours: int = 8
    auth_cookie_name: str = "access_token"
    # Прод-режим должен слать cookie только по HTTPS. Dev (debug=True) → False.
    auth_cookie_secure: Optional[bool] = None
    auth_cookie_samesite: str = "lax"

    # Admin seed (used by scripts/create_admin.py)
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_aliases(cls, value: Any) -> Any:
        """Accept environment-style aliases for the debug flag."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"debug", "dev", "development", "local"}:
                return True
            if normalized in {"release", "prod", "production"}:
                return False
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Accept either JSON array or comma-separated CORS origins."""
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            return []

        if normalized.startswith("["):
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return parsed

        return [
            origin.strip()
            for origin in normalized.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def _enforce_jwt_secret(self) -> "Settings":
        """Production must override the JWT secret; dev gets a stable fallback."""
        placeholder = "dev-secret-change-in-production"
        if not self.debug:
            if not self.jwt_secret_key or self.jwt_secret_key == placeholder:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a non-default value when DEBUG is false"
                )
        elif not self.jwt_secret_key:
            self.jwt_secret_key = placeholder
        if self.auth_cookie_secure is None:
            self.auth_cookie_secure = not self.debug
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
