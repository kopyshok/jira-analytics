"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Application
    app_name: str = "Jira Analytics"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # Database
    database_url: str = Field(
        default="sqlite:///./data/jira_analytics.db",
        description="SQLite database URL"
    )
    
    # Jira Cloud
    jira_base_url: Optional[str] = Field(default=None)
    jira_email: Optional[str] = Field(default=None)
    jira_api_token: Optional[str] = Field(default=None)
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Paths
    data_dir: Path = Path("./data")
    exports_dir: Path = Path("./exports")
    
    def setup_directories(self) -> None:
        """Create necessary directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.setup_directories()
    return settings
