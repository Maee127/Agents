"""Speaker-role assignment exception hierarchy.

Messages are log-safe by design: they must not include transcript text, audio
paths, phone numbers, customer identifiers, or raw payload details.
"""

from sales_call_agent.domain.exceptions import DomainError


class SpeakerIdentityError(DomainError):
    """Base class for speaker-role assignment failures. Never raised directly."""


class InvalidRoleAssignmentInputError(SpeakerIdentityError):
    """Raised when role-assignment inputs are invalid or contradictory."""


class InvalidRoleEvidenceError(SpeakerIdentityError):
    """Raised when role evidence entries are malformed or inconsistent."""


class InvalidRoleAssignmentResultError(SpeakerIdentityError):
    """Raised when role-assignment output violates result invariants."""


class UnsupportedRoleAssignmentConfigurationError(SpeakerIdentityError):
    """Raised when role-assignment configuration values are invalid."""
