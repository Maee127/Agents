"""Core domain models for calls, audio assets, and processing states.

``CallMetadata`` mirrors the canonical metadata schema in
``docs/project-specification.md`` (section 3) verbatim. Validation is strict
and non-coercing: enum fields require real enum members, identifiers are
preserved exactly as given, and all error messages are log-safe (field and
status names only, never values).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum, StrEnum

from sales_call_agent.domain.exceptions import (
    DomainError,
    InvalidAudioAssetError,
    InvalidCallError,
    InvalidCallMetadataError,
    InvalidStatusTransitionError,
)


class SourceType(StrEnum):
    """Origin of a call recording, per the canonical metadata schema."""

    RECORDER_APP = "recorder_app"
    CDR_SOFTWARE = "cdr_software"


class AudioChannels(StrEnum):
    """Channel layout of a recording; determines whether diarization is required."""

    MONO = "mono"
    STEREO = "stereo"


class CallProcessingStatus(StrEnum):
    """Completed business-pipeline stage of a call.

    Represents business-stage completion, not the worker/orchestration
    lifecycle. Operational and retry states may be modeled separately when
    queue-based processing is implemented (see ``docs/decisions.md``).
    """

    RECEIVED = "received"
    VALIDATED = "validated"
    TRANSCRIBED = "transcribed"
    DIARIZED = "diarized"
    ROLES_ASSIGNED = "roles_assigned"
    EVALUATED = "evaluated"
    REJECTED = "rejected"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Whether no further transitions are allowed from this status."""
        return not _VALID_TRANSITIONS[self]

    def can_transition_to(self, new_status: CallProcessingStatus) -> bool:
        """Whether moving from this status to ``new_status`` is a legal transition."""
        return new_status in _VALID_TRANSITIONS[self]


_VALID_TRANSITIONS: dict[CallProcessingStatus, frozenset[CallProcessingStatus]] = {
    CallProcessingStatus.RECEIVED: frozenset(
        {
            CallProcessingStatus.VALIDATED,
            CallProcessingStatus.REJECTED,
            CallProcessingStatus.FAILED,
        }
    ),
    CallProcessingStatus.VALIDATED: frozenset(
        {CallProcessingStatus.TRANSCRIBED, CallProcessingStatus.FAILED}
    ),
    CallProcessingStatus.TRANSCRIBED: frozenset(
        {CallProcessingStatus.DIARIZED, CallProcessingStatus.FAILED}
    ),
    CallProcessingStatus.DIARIZED: frozenset(
        {CallProcessingStatus.ROLES_ASSIGNED, CallProcessingStatus.FAILED}
    ),
    CallProcessingStatus.ROLES_ASSIGNED: frozenset(
        {CallProcessingStatus.EVALUATED, CallProcessingStatus.FAILED}
    ),
    CallProcessingStatus.EVALUATED: frozenset(),
    CallProcessingStatus.REJECTED: frozenset(),
    CallProcessingStatus.FAILED: frozenset(),
}


def _check_required_string(value: object, field_name: str, error: type[DomainError]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")


def _check_optional_string(value: object, field_name: str, error: type[DomainError]) -> None:
    if value is not None:
        _check_required_string(value, field_name, error)


def _check_enum_member(
    value: object, enum_cls: type[Enum], field_name: str, error: type[DomainError]
) -> None:
    if not isinstance(value, enum_cls):
        raise error(f"{field_name} must be a {enum_cls.__name__} member")


def _check_finite_duration(value: object, field_name: str, error: type[DomainError]) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error(f"{field_name} must be a number")
    if not math.isfinite(value):
        raise error(f"{field_name} must be finite")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _check_aware_timestamp(value: object, field_name: str, error: type[DomainError]) -> None:
    if not isinstance(value, datetime):
        raise error(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error(f"{field_name} must be timezone-aware with an effective UTC offset")


@dataclass(frozen=True, slots=True, kw_only=True)
class CallMetadata:
    """Canonical metadata record produced by source-specific ingestion parsers.

    Field set and names follow the specification's canonical metadata schema
    verbatim. ``seller_number`` is deliberately the only seller identifier
    here: the ``seller_number`` vs ``seller_id`` question is an open decision
    (see ``docs/decisions.md``) and must not be resolved silently.

    ``seller_number``, ``counterparty_phone``, ``original_filename``, and
    ``storage_path`` are PII-bearing (filenames and paths often embed the
    counterparty phone number) and are excluded from ``repr``/``str``.
    """

    call_id: str
    seller_number: str = field(repr=False)
    source_type: SourceType
    call_timestamp: datetime
    duration_seconds: float
    counterparty_phone: str | None = field(repr=False, default=None)
    original_filename: str = field(repr=False)
    audio_channels: AudioChannels
    storage_path: str = field(repr=False)

    def __post_init__(self) -> None:
        _check_required_string(self.call_id, "call_id", InvalidCallMetadataError)
        _check_required_string(self.seller_number, "seller_number", InvalidCallMetadataError)
        _check_required_string(
            self.original_filename, "original_filename", InvalidCallMetadataError
        )
        _check_required_string(self.storage_path, "storage_path", InvalidCallMetadataError)
        _check_optional_string(
            self.counterparty_phone, "counterparty_phone", InvalidCallMetadataError
        )
        _check_enum_member(self.source_type, SourceType, "source_type", InvalidCallMetadataError)
        _check_enum_member(
            self.audio_channels, AudioChannels, "audio_channels", InvalidCallMetadataError
        )
        _check_aware_timestamp(self.call_timestamp, "call_timestamp", InvalidCallMetadataError)
        _check_finite_duration(self.duration_seconds, "duration_seconds", InvalidCallMetadataError)


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioAsset:
    """A stored call recording referenced by the pipeline.

    ``content_hash`` supports the specification's hash-based duplicate
    detection; its algorithm and format are chosen by ingestion and are
    opaque to the domain. ``storage_path`` is excluded from ``repr``/``str``
    because paths can embed phone numbers.
    """

    storage_path: str = field(repr=False)
    audio_channels: AudioChannels
    content_hash: str

    def __post_init__(self) -> None:
        _check_required_string(self.storage_path, "storage_path", InvalidAudioAssetError)
        _check_required_string(self.content_hash, "content_hash", InvalidAudioAssetError)
        _check_enum_member(
            self.audio_channels, AudioChannels, "audio_channels", InvalidAudioAssetError
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Call:
    """Aggregate tying canonical metadata, stored audio, and pipeline status together."""

    metadata: CallMetadata
    audio: AudioAsset
    status: CallProcessingStatus = CallProcessingStatus.RECEIVED

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, CallMetadata):
            raise InvalidCallError("metadata must be a CallMetadata instance")
        if not isinstance(self.audio, AudioAsset):
            raise InvalidCallError("audio must be an AudioAsset instance")
        _check_enum_member(self.status, CallProcessingStatus, "status", InvalidCallError)
        if self.audio.storage_path != self.metadata.storage_path:
            raise InvalidCallError("audio.storage_path must match metadata.storage_path")
        if self.audio.audio_channels != self.metadata.audio_channels:
            raise InvalidCallError("audio.audio_channels must match metadata.audio_channels")

    @property
    def call_id(self) -> str:
        """Opaque identifier of the call, owned by the canonical metadata."""
        return self.metadata.call_id

    def advance_to(self, new_status: CallProcessingStatus) -> Call:
        """Return a copy of this call moved to ``new_status``.

        Raises ``InvalidCallError`` if ``new_status`` is not a
        ``CallProcessingStatus`` member, and ``InvalidStatusTransitionError``
        if the transition is not legal from the current status.
        """
        _check_enum_member(new_status, CallProcessingStatus, "new_status", InvalidCallError)
        if not self.status.can_transition_to(new_status):
            raise InvalidStatusTransitionError(self.status, new_status)
        return replace(self, status=new_status)
