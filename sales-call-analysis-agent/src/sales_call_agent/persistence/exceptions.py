"""Persistence exception taxonomy with log-safe error messages."""

from sales_call_agent.domain.exceptions import DomainError


class PersistenceError(DomainError):
    """Base class for provider-independent persistence errors."""


class InvalidPersistenceInputError(PersistenceError):
    """Raised when persistence input or key material is invalid."""


class RecordNotFoundError(PersistenceError):
    """Raised when a requested record does not exist."""


class PersistenceConflictError(PersistenceError):
    """Base class for optimistic/idempotency conflict errors."""


class RecordAlreadyExistsError(PersistenceConflictError):
    """Raised when an immutable key already stores a different value."""


class StaleRecordVersionError(PersistenceConflictError):
    """Raised when expected revision does not match current revision."""


class RepositoryUnavailableError(PersistenceError):
    """Raised when a repository is intentionally unavailable in tests."""
