"""Alembic migration environment.

The database URL is injected from the ALEMBIC_DATABASE_URL environment variable.
Do not print the URL or include it in error messages.

Tables are registered against the shared MetaData by importing the tables module.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import tables module to register all Table objects against metadata.
# The unused alias is intentional — importing the module is the registration act.
from sales_call_agent.infrastructure.postgres import tables as _tables  # noqa: F401
from sales_call_agent.infrastructure.postgres.metadata import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata

database_url = os.environ.get("ALEMBIC_DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "ALEMBIC_DATABASE_URL environment variable is required for migrations. "
        "Do not include credentials in alembic.ini."
    )

# Replace % with %% to avoid ConfigParser interpolation errors for psycopg DSNs.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
