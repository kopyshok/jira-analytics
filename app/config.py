"""Application configuration."""

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Jira Analytics"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite:///./data/jira_analytics.db"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Jira Cloud credentials
    jira_base_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    
    # Sync settings
    jira_request_delay: float = 0.1  # 100ms between requests
    jira_max_retries: int = 3
    jira_batch_size: int = 100  # Issues per request

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
