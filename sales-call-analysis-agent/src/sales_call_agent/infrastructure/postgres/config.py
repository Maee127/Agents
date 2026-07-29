"""PostgreSQL adapter configuration.

Credentials are wrapped in SecretStr and never appear in repr, logs,
or exception messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import SecretStr


@dataclass(frozen=True, slots=True, kw_only=True)
class PostgresConfig:
    """Injected configuration for the PostgreSQL adapter.

    Only the fields that are actively used are included.
    pool_size and pool_timeout_seconds are passed to the SQLAlchemy engine.
    """

    database_url: SecretStr = field(repr=False)
    pool_size: int = 5
    pool_timeout_seconds: float = 30.0
