"""Application configuration."""

import json
from functools import lru_cache
from typing import Annotated, Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Jira Analytics"
    app_version: str = "0.1.0"
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
