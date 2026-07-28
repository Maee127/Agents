"""Provider-independent diarization request/result models."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import TYPE_CHECKING, Protocol

from sales_call_agent.diarization.exceptions import (
    InvalidDiarizationInputError,
    InvalidDiarizationResponseError,
    UnsupportedSpeakerConstraintError,
)

if TYPE_CHECKING:

    class _NormalizedArtifactMetadata(Protocol):
        call_id: str

    class _NormalizedArtifactSource(Protocol):
        metadata: _NormalizedArtifactMetadata

    class _NormalizedArtifactAudio(Protocol):
        storage_path: str
        content_hash: str

    class NormalizedArtifact(Protocol):
        source: _NormalizedArtifactSource
        normalized_audio: _NormalizedArtifactAudio


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SPEAKER_LABEL_RE = re.compile(r"^SPEAKER_[0-9]{2,}$")


class DiarizationQualityFlag(StrEnum):
    """Quality or completeness conditions reported by diarization providers."""

    NO_SPEECH_SEGMENTS = "no_speech_segments"
    SINGLE_SPEAKER_DETECTED = "single_speaker_detected"
    OVERLAPPING_SPEECH_DETECTED = "overlapping_speech_detected"
    SPEAKER_COUNT_UNCERTAIN = "speaker_count_uncertain"
    VERY_SHORT_TURNS_PRESENT = "very_short_turns_present"
    PARTIAL_RESULT = "partial_result"
    PROVIDER_WARNING = "provider_warning"


class DiarizationConfidenceScale(StrEnum):
    """Closed set of confidence value scales."""

    ZERO_TO_ONE = "zero_to_one"
    PERCENTAGE = "percentage"
    LOG_PROBABILITY = "log_probability"
    UNSPECIFIED = "unspecified"


def _ensure_required_string(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")


def _ensure_optional_string(value: object, field_name: str, error: type[Exception]) -> None:
    if value is not None:
        _ensure_required_string(value, field_name, error)


def _ensure_enum_member(
    value: object, enum_type: type[Enum], field_name: str, error: type[Exception]
) -> None:
    if not isinstance(value, enum_type):
        raise error(f"{field_name} must be a {enum_type.__name__} member")


def _ensure_finite_non_negative_timestamp(
    value: object, field_name: str, error: type[Exception]
) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error(f"{field_name} must be a number")
    if not math.isfinite(value):
        raise error(f"{field_name} must be finite")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _ensure_positive_int(value: object, field_name: str, error: type[Exception]) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error(f"{field_name} must be an integer")
    if value < 1:
        raise error(f"{field_name} must be at least 1")


def _ensure_safe_identifier(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe identifier")


def _ensure_speaker_label(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not _SPEAKER_LABEL_RE.fullmatch(value):
        raise error(f"{field_name} must match the canonical speaker label format")


@dataclass(frozen=True, slots=True, kw_only=True)
class DiarizationConfidenceMetric:
    """Provider-native confidence metric that is not assumed cross-provider comparable."""

    name: str
    value: float
    scale: DiarizationConfidenceScale = DiarizationConfidenceScale.UNSPECIFIED
    higher_is_better: bool | None = None

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.name, "name", InvalidDiarizationResponseError)
        _ensure_enum_member(
            self.scale, DiarizationConfidenceScale, "scale", InvalidDiarizationResponseError
        )
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise InvalidDiarizationResponseError("value must be a number")
        if not math.isfinite(self.value):
            raise InvalidDiarizationResponseError("value must be finite")
        if self.scale is DiarizationConfidenceScale.ZERO_TO_ONE and not (0.0 <= self.value <= 1.0):
            raise InvalidDiarizationResponseError("value must be between 0.0 and 1.0")
        if self.scale is DiarizationConfidenceScale.PERCENTAGE and not (0.0 <= self.value <= 100.0):
            raise InvalidDiarizationResponseError("value must be between 0.0 and 100.0")
        if self.higher_is_better is not None and not isinstance(self.higher_is_better, bool):
            raise InvalidDiarizationResponseError("higher_is_better must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeakerTurn:
    """Anonymous speaker-labelled time range within one call."""

    speaker_label: str
    start_seconds: float
    end_seconds: float
    provider_confidence: tuple[DiarizationConfidenceMetric, ...] = ()

    def __post_init__(self) -> None:
        _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidDiarizationResponseError)
        _ensure_finite_non_negative_timestamp(
            self.start_seconds, "start_seconds", InvalidDiarizationResponseError
        )
        _ensure_finite_non_negative_timestamp(
            self.end_seconds, "end_seconds", InvalidDiarizationResponseError
        )
        if self.end_seconds <= self.start_seconds:
            raise InvalidDiarizationResponseError("end_seconds must be greater than start_seconds")
        for metric in self.provider_confidence:
            if not isinstance(metric, DiarizationConfidenceMetric):
                raise InvalidDiarizationResponseError(
                    "provider_confidence must contain DiarizationConfidenceMetric values"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class DiarizationRequest:
    """Provider-facing request for diarizing an already normalized artifact."""

    call_id: str
    normalized_audio_path: str = field(repr=False)
    normalized_audio_hash: str
    audio_duration_seconds: float | None = None
    min_expected_speakers: int | None = None
    max_expected_speakers: int | None = None
    exact_expected_speakers: int | None = None
    provider_config_id: str | None = None

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidDiarizationInputError)
        _ensure_required_string(
            self.normalized_audio_path, "normalized_audio_path", InvalidDiarizationInputError
        )
        _ensure_required_string(
            self.normalized_audio_hash, "normalized_audio_hash", InvalidDiarizationInputError
        )
        _ensure_optional_string(
            self.provider_config_id, "provider_config_id", InvalidDiarizationInputError
        )
        if self.audio_duration_seconds is not None:
            _ensure_finite_non_negative_timestamp(
                self.audio_duration_seconds,
                "audio_duration_seconds",
                InvalidDiarizationInputError,
            )
            if self.audio_duration_seconds <= 0:
                raise InvalidDiarizationInputError(
                    "audio_duration_seconds must be greater than zero"
                )

        has_exact = self.exact_expected_speakers is not None
        has_range = self.min_expected_speakers is not None or self.max_expected_speakers is not None
        if has_exact and has_range:
            raise UnsupportedSpeakerConstraintError(
                "exact_expected_speakers cannot be combined with min/max speaker constraints"
            )

        if self.exact_expected_speakers is not None:
            _ensure_positive_int(
                self.exact_expected_speakers,
                "exact_expected_speakers",
                UnsupportedSpeakerConstraintError,
            )

        if self.min_expected_speakers is not None:
            _ensure_positive_int(
                self.min_expected_speakers,
                "min_expected_speakers",
                UnsupportedSpeakerConstraintError,
            )
        if self.max_expected_speakers is not None:
            _ensure_positive_int(
                self.max_expected_speakers,
                "max_expected_speakers",
                UnsupportedSpeakerConstraintError,
            )
        if (
            self.min_expected_speakers is not None
            and self.max_expected_speakers is not None
            and self.min_expected_speakers > self.max_expected_speakers
        ):
            raise UnsupportedSpeakerConstraintError(
                "min_expected_speakers must not exceed max_expected_speakers"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class DiarizationResult:
    """Provider-independent diarization result."""

    call_id: str
    turns: tuple[SpeakerTurn, ...]
    provider_name: str
    model_name: str
    processing_duration_seconds: float | None = None
    provider_confidence: tuple[DiarizationConfidenceMetric, ...] = ()
    quality_flags: tuple[DiarizationQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidDiarizationResponseError)
        _ensure_required_string(
            self.provider_name, "provider_name", InvalidDiarizationResponseError
        )
        _ensure_required_string(self.model_name, "model_name", InvalidDiarizationResponseError)
        if self.processing_duration_seconds is not None:
            _ensure_finite_non_negative_timestamp(
                self.processing_duration_seconds,
                "processing_duration_seconds",
                InvalidDiarizationResponseError,
            )
        for metric in self.provider_confidence:
            if not isinstance(metric, DiarizationConfidenceMetric):
                raise InvalidDiarizationResponseError(
                    "provider_confidence must contain DiarizationConfidenceMetric values"
                )
        for flag in self.quality_flags:
            _ensure_enum_member(
                flag, DiarizationQualityFlag, "quality_flags", InvalidDiarizationResponseError
            )
        for code in self.warning_codes:
            _ensure_safe_identifier(code, "warning_codes", InvalidDiarizationResponseError)

        _validate_turn_sequence(self.turns)
        _validate_quality_flag_consistency(self.turns, self.quality_flags)

    @property
    def speaker_count(self) -> int:
        """Number of unique anonymous speaker labels present in ``turns``."""
        return len({turn.speaker_label for turn in self.turns})


def diarization_request_from_normalized_artifact(
    normalized: NormalizedArtifact,
    *,
    audio_duration_seconds: float | None = None,
    min_expected_speakers: int | None = None,
    max_expected_speakers: int | None = None,
    exact_expected_speakers: int | None = None,
    provider_config_id: str | None = None,
) -> DiarizationRequest:
    """Build a request from a normalized-audio contract object.

    Accepts any object that provides:
    - ``source.metadata.call_id``
    - ``normalized_audio.storage_path``
    - ``normalized_audio.content_hash``
    """
    source = getattr(normalized, "source", None)
    if source is None:
        raise InvalidDiarizationInputError("normalized artifact is missing required fields")

    metadata = getattr(source, "metadata", None)
    normalized_audio = getattr(normalized, "normalized_audio", None)
    if metadata is None or normalized_audio is None:
        raise InvalidDiarizationInputError("normalized artifact is missing required fields")

    call_id = getattr(metadata, "call_id", None)
    path = getattr(normalized_audio, "storage_path", None)
    content_hash = getattr(normalized_audio, "content_hash", None)
    if not isinstance(call_id, str) or not call_id:
        raise InvalidDiarizationInputError("normalized artifact is missing required fields")
    if not isinstance(path, str) or not path:
        raise InvalidDiarizationInputError("normalized artifact is missing required fields")
    if not isinstance(content_hash, str) or not content_hash:
        raise InvalidDiarizationInputError("normalized artifact is missing required fields")

    return DiarizationRequest(
        call_id=call_id,
        normalized_audio_path=path,
        normalized_audio_hash=content_hash,
        audio_duration_seconds=audio_duration_seconds,
        min_expected_speakers=min_expected_speakers,
        max_expected_speakers=max_expected_speakers,
        exact_expected_speakers=exact_expected_speakers,
        provider_config_id=provider_config_id,
    )


def validate_turns_within_audio_duration(
    turns: Sequence[SpeakerTurn],
    audio_duration_seconds: float,
) -> None:
    """Validate that all turns fit within a known audio duration.

    Intended for adapter/boundary use before publishing a ``DiarizationResult``.
    """
    _ensure_finite_non_negative_timestamp(
        audio_duration_seconds,
        "audio_duration_seconds",
        InvalidDiarizationResponseError,
    )
    if audio_duration_seconds <= 0:
        raise InvalidDiarizationResponseError("audio_duration_seconds must be greater than zero")

    for turn in turns:
        if turn.start_seconds > audio_duration_seconds:
            raise InvalidDiarizationResponseError("turn start exceeds audio duration")
        if turn.end_seconds > audio_duration_seconds:
            raise InvalidDiarizationResponseError("turn end exceeds audio duration")


def has_cross_speaker_overlap(turns: Sequence[SpeakerTurn]) -> bool:
    """Return True when any two turns from different speakers overlap in time."""
    for left_index, left_turn in enumerate(turns):
        for right_turn in turns[left_index + 1 :]:
            if left_turn.speaker_label == right_turn.speaker_label:
                continue
            if _intervals_overlap(
                left_turn.start_seconds,
                left_turn.end_seconds,
                right_turn.start_seconds,
                right_turn.end_seconds,
            ):
                return True
    return False


def _validate_turn_sequence(turns: Sequence[SpeakerTurn]) -> None:
    seen: set[tuple[str, float, float]] = set()
    previous_start = 0.0
    for index, turn in enumerate(turns):
        if not isinstance(turn, SpeakerTurn):
            raise InvalidDiarizationResponseError("turns must contain SpeakerTurn values")
        if index > 0 and turn.start_seconds < previous_start:
            raise InvalidDiarizationResponseError("turn start times must be non-decreasing")
        previous_start = turn.start_seconds
        key = (turn.speaker_label, turn.start_seconds, turn.end_seconds)
        if key in seen:
            raise InvalidDiarizationResponseError("duplicate speaker turns are not allowed")
        seen.add(key)


def _validate_quality_flag_consistency(
    turns: Sequence[SpeakerTurn],
    quality_flags: Sequence[DiarizationQualityFlag],
) -> None:
    flag_set = set(quality_flags)
    has_no_speech = DiarizationQualityFlag.NO_SPEECH_SEGMENTS in flag_set
    has_overlap = DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED in flag_set
    has_single = DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED in flag_set
    cross_speaker_overlap = has_cross_speaker_overlap(turns)
    unique_speakers = len({turn.speaker_label for turn in turns})

    if not turns:
        if not has_no_speech:
            raise InvalidDiarizationResponseError(
                "empty turns require NO_SPEECH_SEGMENTS quality flag"
            )
        if has_overlap or has_single:
            raise InvalidDiarizationResponseError(
                "NO_SPEECH_SEGMENTS cannot be combined with speaker activity flags"
            )
        return

    if has_no_speech:
        raise InvalidDiarizationResponseError(
            "NO_SPEECH_SEGMENTS cannot be set when turns are present"
        )

    if cross_speaker_overlap and not has_overlap:
        raise InvalidDiarizationResponseError(
            "cross-speaker overlap requires OVERLAPPING_SPEECH_DETECTED quality flag"
        )
    if has_overlap and not cross_speaker_overlap:
        raise InvalidDiarizationResponseError(
            "OVERLAPPING_SPEECH_DETECTED requires cross-speaker overlap in turns"
        )

    if unique_speakers == 1 and not has_single:
        raise InvalidDiarizationResponseError(
            "single detected speaker requires SINGLE_SPEAKER_DETECTED quality flag"
        )
    if unique_speakers != 1 and has_single:
        raise InvalidDiarizationResponseError(
            "SINGLE_SPEAKER_DETECTED requires exactly one detected speaker"
        )


def _intervals_overlap(
    left_start: float,
    left_end: float,
    right_start: float,
    right_end: float,
) -> bool:
    return left_start < right_end and right_start < left_end
