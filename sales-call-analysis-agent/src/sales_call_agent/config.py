"""Application configuration loaded from environment variables."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the sales call analysis agent.

    Values are read from environment variables prefixed with ``APP_``
    (e.g. ``APP_ENVIRONMENT``), then from a local ``.env`` file if present,
    and finally fall back to the safe local-development defaults below.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "sales-call-analysis-agent"
    environment: str = "development"
    debug: bool = False

    # SecretStr keeps credentials embedded in the URL out of repr/str/logs.
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://postgres:postgres@localhost:5432/sales_calls"),
        description="PostgreSQL connection URL in SQLAlchemy format (psycopg driver).",
    )


def get_settings() -> Settings:
    """Build a fresh :class:`Settings` instance from the current environment."""
    return Settings()
