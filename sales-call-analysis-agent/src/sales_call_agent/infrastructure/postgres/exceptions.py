"""Database exception translation for the PostgreSQL adapter.

Maps known psycopg/SQLAlchemy integrity and connectivity errors to
persistence boundary exceptions.  Programming errors are not broadly wrapped.

Exception messages never contain SQL, bind parameters, storage paths,
phone numbers, transcript text, or any PII.
"""

from __future__ import annotations

from sales_call_agent.persistence.exceptions import RepositoryUnavailableError


# psycopg3 SQLSTATE codes for expected integrity violations
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_CHECK_VIOLATION = "23514"
_NOT_NULL_VIOLATION = "23502"


def is_unique_violation(exc: Exception) -> bool:
    """Return True iff exc is a psycopg unique-constraint violation (23505)."""
    return _get_sqlstate(exc) == _UNIQUE_VIOLATION


def is_integrity_violation(exc: Exception) -> bool:
    """Return True iff exc is any kind of integrity error."""
    return _get_sqlstate(exc) in (
        _UNIQUE_VIOLATION,
        _FOREIGN_KEY_VIOLATION,
        _CHECK_VIOLATION,
        _NOT_NULL_VIOLATION,
    )


def translate_connectivity_error(exc: Exception) -> RepositoryUnavailableError | None:
    """Map transient connectivity failures to RepositoryUnavailableError.

    Returns None if the exception is not a known connectivity error
    (the caller should let it propagate as a programming error).
    """
    try:
        from sqlalchemy.exc import DisconnectionError, OperationalError
    except ImportError:
        return None

    if isinstance(exc, (OperationalError, DisconnectionError)):
        # Do not include exc details — they may contain DSN or SQL fragments.
        return RepositoryUnavailableError("repository unavailable")
    return None


def _get_sqlstate(exc: Exception) -> str | None:
    """Extract the SQLSTATE code from a psycopg/SQLAlchemy exception."""
    # SQLAlchemy wraps psycopg errors; the original is in exc.orig
    orig = getattr(exc, "orig", exc)
    # psycopg3 exposes sqlstate on the exception directly
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate is not None:
        return str(sqlstate)
    # psycopg3 also uses diag.sqlstate
    diag = getattr(orig, "diag", None)
    if diag is not None:
        return str(getattr(diag, "sqlstate", None))
    return None
