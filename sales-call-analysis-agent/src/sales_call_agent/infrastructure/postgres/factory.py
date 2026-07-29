"""Engine factory and PostgreSQL UnitOfWork factory.

The engine is created once per factory instance; connections are acquired
per UnitOfWork call.  Credentials never appear in repr or exception messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, create_engine

from sales_call_agent.infrastructure.postgres.config import PostgresConfig
from sales_call_agent.infrastructure.postgres.unit_of_work import PostgresUnitOfWork


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


@dataclass(frozen=True, slots=True, kw_only=True)
class PostgresUnitOfWorkFactory:
    """Callable factory that produces a fresh PostgresUnitOfWork per call.

    The engine is held repr=False to prevent credential leakage via repr.
    One engine (connection pool) is shared across all UoW instances.
    """

    engine: Engine = field(repr=False)

    def __call__(self) -> PostgresUnitOfWork:
        connection = self.engine.connect()
        transaction = connection.begin()
        return PostgresUnitOfWork(connection=connection, transaction=transaction)
