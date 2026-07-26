"""Transcription-specific exception hierarchy.

Messages are log-safe by design: they must not include audio paths, filenames,
phone numbers, transcript text, provider secrets, or raw provider payloads.
"""

from sales_call_agent.domain.exceptions import DomainError


class TranscriptionError(DomainError):
    """Base class for transcription failures. Never raised directly."""


class InvalidTranscriptionInputError(TranscriptionError):
    """Raised when the transcription request/input contract is invalid."""


class TranscriptionProviderUnavailableError(TranscriptionError):
    """Raised when the provider is unavailable or misconfigured."""


class TranscriptionTimeoutError(TranscriptionError):
    """Raised when the provider times out."""


class TranscriptionRequestFailedError(TranscriptionError):
    """Raised when the provider request fails for an operational reason."""


class UnsupportedTranscriptionLanguageError(TranscriptionError):
    """Raised when the requested/expected language is unsupported."""


class InvalidTranscriptionResponseError(TranscriptionError):
    """Raised when provider output cannot be mapped to a valid transcription result."""
