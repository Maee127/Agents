"""Alignment-specific exception hierarchy.

Messages are log-safe by design: they must not include transcript text, audio
paths, provider payloads, model/cache paths, or customer identifiers.
"""

from sales_call_agent.domain.exceptions import DomainError


class AlignmentError(DomainError):
    """Base class for alignment failures. Never raised directly."""


class InvalidAlignmentInputError(AlignmentError):
    """Raised when alignment input contracts are invalid or contradictory."""


class InvalidAlignmentResultError(AlignmentError):
    """Raised when aligned output cannot be represented as a valid result."""


class UnsupportedAlignmentConfigurationError(AlignmentError):
    """Raised when alignment configuration values are invalid."""
