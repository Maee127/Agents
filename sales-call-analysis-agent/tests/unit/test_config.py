"""Smoke tests for application configuration."""

import pytest

from sales_call_agent.config import Settings


def make_settings() -> Settings:
    """Build settings without reading a local .env file, so tests are hermetic."""
    return Settings(_env_file=None)


def test_default_settings_load() -> None:
    settings = make_settings()

    assert settings.app_name == "sales-call-analysis-agent"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "staging")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+psycopg://u:pw@db:5432/other")

    settings = make_settings()

    assert settings.environment == "staging"
    assert settings.debug is True
    assert settings.database_url.get_secret_value() == "postgresql+psycopg://u:pw@db:5432/other"


def test_secrets_are_not_exposed_in_repr_or_str(monkeypatch: pytest.MonkeyPatch) -> None:
    password = "super-secret-password"
    monkeypatch.setenv("APP_DATABASE_URL", f"postgresql+psycopg://user:{password}@db:5432/calls")

    settings = make_settings()

    assert password not in repr(settings)
    assert password not in str(settings)
    assert password not in str(settings.database_url)
    assert password in settings.database_url.get_secret_value()
