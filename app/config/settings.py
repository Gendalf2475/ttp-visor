from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings.

    Operational configuration lives in config.yml; secrets and deployment-specific
    values stay in .env.
    """

    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    config_path: Path = Field(default=Path("config.yml"), alias="CONFIG_PATH")
    google_credentials_file: Path | None = Field(default=None, alias="GOOGLE_CREDENTIALS_FILE")
    google_credentials_json: str | None = Field(default=None, alias="GOOGLE_CREDENTIALS_JSON")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

