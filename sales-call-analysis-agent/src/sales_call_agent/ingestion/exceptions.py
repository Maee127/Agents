"""Ingestion-specific domain errors for local audio file intake.

Messages are log-safe: they never include file paths or filenames, which can
embed phone numbers (PII).
"""

from sales_call_agent.domain.exceptions import DomainError


class IngestionError(DomainError):
    """Base class for ingestion failures. Never raised directly."""


class MissingAudioFileError(IngestionError):
    """Raised when the given path does not exist or is not a regular file."""


class EmptyAudioFileError(IngestionError):
    """Raised when the audio file exists but contains no data."""


class UnsupportedAudioFormatError(IngestionError):
    """Raised when the file extension or channel layout is not supported."""


class CorruptAudioFileError(IngestionError):
    """Raised when the file cannot be read as valid audio."""
