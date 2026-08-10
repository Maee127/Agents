"""PostgreSQL engine factory.

Credentials never appear in repr or exception messages.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

from sales_call_agent.infrastructure.postgres.config import PostgresConfig


def create_postgres_engine(config: PostgresConfig) -> Engine:
    """Create a synchronous SQLAlchemy engine from an injected config.

    The database URL is extracted from SecretStr exactly once here.
    echo=False is always enforced — no SQL logging.
    """
    return create_engine(
        config.database_url.get_secret_value(),
        pool_size=config.pool_size,
        pool_timeout=config.pool_timeout_seconds,
        echo=False,
        future=True,
    )
