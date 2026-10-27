"""Application settings, read from environment variables prefixed with LIFELOG_."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIFELOG_", env_file=".env")

    log_level: str = "INFO"
