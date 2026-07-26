"""Provider-independent transcription request/result models."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionInputError,
    InvalidTranscriptionResponseError,
)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class TranscriptionQualityFlag(StrEnum):
    """Quality or completeness conditions reported by transcription providers."""

    NO_SPEECH_DETECTED = "no_speech_detected"
    TIMESTAMPS_MISSING = "timestamps_missing"
    PARTIAL_RESULT = "partial_result"
    LOW_AUDIO_QUALITY = "low_audio_quality"
    PROVIDER_WARNING = "provider_warning"


class ConfidenceScale(StrEnum):
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


def _ensure_safe_warning_code(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe warning code")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderConfidenceMetric:
    """Provider-native confidence metric that is not assumed cross-provider comparable."""

    name: str
    value: float
    scale: ConfidenceScale = ConfidenceScale.UNSPECIFIED
    higher_is_better: bool | None = None

    def __post_init__(self) -> None:
        _ensure_required_string(self.name, "name", InvalidTranscriptionResponseError)
        _ensure_enum_member(self.scale, ConfidenceScale, "scale", InvalidTranscriptionResponseError)
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise InvalidTranscriptionResponseError("value must be a number")
        if not math.isfinite(self.value):
            raise InvalidTranscriptionResponseError("value must be finite")
        if self.scale is ConfidenceScale.ZERO_TO_ONE and not (0.0 <= self.value <= 1.0):
            raise InvalidTranscriptionResponseError("value must be between 0.0 and 1.0")
        if self.scale is ConfidenceScale.PERCENTAGE and not (0.0 <= self.value <= 100.0):
            raise InvalidTranscriptionResponseError("value must be between 0.0 and 100.0")
        if self.higher_is_better is not None and not isinstance(self.higher_is_better, bool):
            raise InvalidTranscriptionResponseError("higher_is_better must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptWord:
    """Single token/word within a transcript segment."""

    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    provider_confidence: tuple[ProviderConfidenceMetric, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.text, "text", InvalidTranscriptionResponseError)
        has_start = self.start_seconds is not None
        has_end = self.end_seconds is not None
        if has_start != has_end:
            raise InvalidTranscriptionResponseError(
                "start_seconds and end_seconds must be provided together"
            )
        if has_start and has_end:
            _ensure_finite_non_negative_timestamp(
                self.start_seconds, "start_seconds", InvalidTranscriptionResponseError
            )
            _ensure_finite_non_negative_timestamp(
                self.end_seconds, "end_seconds", InvalidTranscriptionResponseError
            )
            if self.end_seconds < self.start_seconds:
                raise InvalidTranscriptionResponseError("end_seconds must be >= start_seconds")
        for metric in self.provider_confidence:
            if not isinstance(metric, ProviderConfidenceMetric):
                raise InvalidTranscriptionResponseError(
                    "provider_confidence must contain ProviderConfidenceMetric values"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptSegment:
    """Time-bounded segment of transcript text."""

    text: str
    start_seconds: float
    end_seconds: float
    words: tuple[TranscriptWord, ...] = ()
    provider_confidence: tuple[ProviderConfidenceMetric, ...] = ()
    quality_flags: tuple[TranscriptionQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.text, "text", InvalidTranscriptionResponseError)
        _ensure_finite_non_negative_timestamp(
            self.start_seconds, "start_seconds", InvalidTranscriptionResponseError
        )
        _ensure_finite_non_negative_timestamp(
            self.end_seconds, "end_seconds", InvalidTranscriptionResponseError
        )
        if self.end_seconds < self.start_seconds:
            raise InvalidTranscriptionResponseError("end_seconds must be >= start_seconds")

        for metric in self.provider_confidence:
            if not isinstance(metric, ProviderConfidenceMetric):
                raise InvalidTranscriptionResponseError(
                    "provider_confidence must contain ProviderConfidenceMetric values"
                )
        for flag in self.quality_flags:
            _ensure_enum_member(
                flag, TranscriptionQualityFlag, "quality_flags", InvalidTranscriptionResponseError
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidTranscriptionResponseError)

        if self.words:
            all_timed = all(word.start_seconds is not None for word in self.words)
            any_timed = any(word.start_seconds is not None for word in self.words)
            if all_timed != any_timed:
                raise InvalidTranscriptionResponseError(
                    "words must be either all timestamped or all untimed"
                )
            if all_timed:
                previous_start = 0.0
                for idx, word in enumerate(self.words):
                    assert word.start_seconds is not None
                    assert word.end_seconds is not None
                    if idx > 0 and word.start_seconds < previous_start:
                        raise InvalidTranscriptionResponseError(
                            "word start times must be non-decreasing"
                        )
                    if (
                        word.start_seconds < self.start_seconds
                        or word.end_seconds > self.end_seconds
                    ):
                        raise InvalidTranscriptionResponseError(
                            "word timestamps must stay within the segment range"
                        )
                    previous_start = word.start_seconds


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptionRequest:
    """Provider-facing request for transcribing an already normalized artifact."""

    call_id: str
    normalized_audio_path: str = field(repr=False)
    normalized_audio_hash: str
    expected_language: str | None = None
    provider_config_id: str | None = None

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidTranscriptionInputError)
        _ensure_required_string(
            self.normalized_audio_path, "normalized_audio_path", InvalidTranscriptionInputError
        )
        _ensure_required_string(
            self.normalized_audio_hash, "normalized_audio_hash", InvalidTranscriptionInputError
        )
        _ensure_optional_string(
            self.expected_language, "expected_language", InvalidTranscriptionInputError
        )
        _ensure_optional_string(
            self.provider_config_id, "provider_config_id", InvalidTranscriptionInputError
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptionResult:
    """Provider-independent transcript result."""

    call_id: str
    full_text: str = field(repr=False)
    segments: tuple[TranscriptSegment, ...]
    detected_language: str | None = None
    language_confidence: float | None = None
    provider_name: str
    model_name: str
    processing_duration_seconds: float | None = None
    provider_confidence: tuple[ProviderConfidenceMetric, ...] = ()
    quality_flags: tuple[TranscriptionQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidTranscriptionResponseError)
        if not isinstance(self.full_text, str):
            raise InvalidTranscriptionResponseError("full_text must be a string")
        if self.full_text and not self.full_text.strip():
            raise InvalidTranscriptionResponseError("full_text must not be whitespace-only")
        _ensure_required_string(
            self.provider_name, "provider_name", InvalidTranscriptionResponseError
        )
        _ensure_required_string(self.model_name, "model_name", InvalidTranscriptionResponseError)
        _ensure_optional_string(
            self.detected_language, "detected_language", InvalidTranscriptionResponseError
        )
        if self.language_confidence is not None:
            _ensure_finite_non_negative_timestamp(
                self.language_confidence, "language_confidence", InvalidTranscriptionResponseError
            )
            if self.language_confidence > 1.0:
                raise InvalidTranscriptionResponseError(
                    "language_confidence must be between 0.0 and 1.0"
                )
        if self.processing_duration_seconds is not None:
            _ensure_finite_non_negative_timestamp(
                self.processing_duration_seconds,
                "processing_duration_seconds",
                InvalidTranscriptionResponseError,
            )
        for metric in self.provider_confidence:
            if not isinstance(metric, ProviderConfidenceMetric):
                raise InvalidTranscriptionResponseError(
                    "provider_confidence must contain ProviderConfidenceMetric values"
                )
        for flag in self.quality_flags:
            _ensure_enum_member(
                flag, TranscriptionQualityFlag, "quality_flags", InvalidTranscriptionResponseError
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidTranscriptionResponseError)

        no_speech_flag = TranscriptionQualityFlag.NO_SPEECH_DETECTED in self.quality_flags
        if self.full_text == "" and self.segments == ():
            if not no_speech_flag:
                raise InvalidTranscriptionResponseError(
                    "empty transcript requires NO_SPEECH_DETECTED quality flag"
                )
        elif self.segments == ():
            raise InvalidTranscriptionResponseError(
                "segments must not be empty unless NO_SPEECH_DETECTED is set"
            )

        previous_start = 0.0
        for idx, segment in enumerate(self.segments):
            if not isinstance(segment, TranscriptSegment):
                raise InvalidTranscriptionResponseError(
                    "segments must contain TranscriptSegment values"
                )
            if idx > 0 and segment.start_seconds < previous_start:
                raise InvalidTranscriptionResponseError(
                    "segment start times must be non-decreasing"
                )
            previous_start = segment.start_seconds


def transcription_request_from_normalized_artifact(
    normalized: object,
    *,
    expected_language: str | None = None,
    provider_config_id: str | None = None,
) -> TranscriptionRequest:
    """Build a request from a normalized-audio contract object.

    Accepts any object that provides:
    - ``source.metadata.call_id``
    - ``normalized_audio.storage_path``
    - ``normalized_audio.content_hash``
    """
    source = getattr(normalized, "source", None)
    metadata = getattr(source, "metadata", None)
    normalized_audio = getattr(normalized, "normalized_audio", None)
    call_id = getattr(metadata, "call_id", None)
    path = getattr(normalized_audio, "storage_path", None)
    content_hash = getattr(normalized_audio, "content_hash", None)
    if not isinstance(call_id, str) or not call_id:
        raise InvalidTranscriptionInputError("normalized artifact is missing required fields")
    if not isinstance(path, str) or not path:
        raise InvalidTranscriptionInputError("normalized artifact is missing required fields")
    if not isinstance(content_hash, str) or not content_hash:
        raise InvalidTranscriptionInputError("normalized artifact is missing required fields")
    return TranscriptionRequest(
        call_id=call_id,
        normalized_audio_path=path,
        normalized_audio_hash=content_hash,
        expected_language=expected_language,
        provider_config_id=provider_config_id,
    )
