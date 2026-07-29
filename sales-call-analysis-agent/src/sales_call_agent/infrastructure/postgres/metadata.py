"""SQLAlchemy MetaData singleton for the PostgreSQL adapter.

All Table objects in tables.py register against this MetaData instance.
Alembic env.py imports this module (and tables) to discover the schema.
"""

from __future__ import annotations

from sqlalchemy import MetaData

# Naming convention for constraints — required for Alembic autogenerate
# and for consistent constraint names across migrations.
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
