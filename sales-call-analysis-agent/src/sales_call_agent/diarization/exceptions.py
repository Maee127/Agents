"""Diarization-specific exception hierarchy.

Messages are log-safe by design: they must not include audio paths, filenames,
phone numbers, provider payloads, model/cache paths, or transcript content.
"""

from sales_call_agent.domain.exceptions import DomainError


class DiarizationError(DomainError):
    """Base class for diarization failures. Never raised directly."""


class InvalidDiarizationInputError(DiarizationError):
    """Raised when the diarization request/input contract is invalid."""


class DiarizationProviderUnavailableError(DiarizationError):
    """Raised when the diarization provider is unavailable or misconfigured."""


class DiarizationTimeoutError(DiarizationError):
    """Raised when the diarization provider times out."""


class DiarizationRequestFailedError(DiarizationError):
    """Raised when the diarization provider request fails for an operational reason."""


class InvalidDiarizationResponseError(DiarizationError):
    """Raised when provider output cannot be mapped to a valid diarization result."""


class UnsupportedSpeakerConstraintError(DiarizationError):
    """Raised when speaker-count constraints on the request are impossible or mixed."""
