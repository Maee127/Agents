"""Provider-independent models for transcript-speaker alignment."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sales_call_agent.alignment.exceptions import (
    InvalidAlignmentInputError,
    InvalidAlignmentResultError,
    UnsupportedAlignmentConfigurationError,
)
from sales_call_agent.diarization.models import DiarizationResult
from sales_call_agent.transcription.models import TranscriptionResult

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SPEAKER_LABEL_RE = re.compile(r"^SPEAKER_[0-9]{2,}$")


class AlignmentMethod(StrEnum):
    """Method used to align one transcript segment."""

    WORD_LEVEL = "word_level"
    SEGMENT_LEVEL = "segment_level"


class AlignmentStatus(StrEnum):
    """Primary alignment outcome for one aligned unit."""

    ASSIGNED = "assigned"
    AMBIGUOUS = "ambiguous"
    UNASSIGNED = "unassigned"


class AlignmentQualityFlag(StrEnum):
    """Quality/completeness conditions for an alignment result."""

    NO_TRANSCRIPT_SPEECH = "no_transcript_speech"
    NO_DIARIZATION_TURNS = "no_diarization_turns"
    UNASSIGNED_CONTENT_PRESENT = "unassigned_content_present"
    AMBIGUOUS_CONTENT_PRESENT = "ambiguous_content_present"
    OVERLAPPING_SPEECH_PRESENT = "overlapping_speech_present"
    SEGMENT_LEVEL_FALLBACK_USED = "segment_level_fallback_used"
    MIXED_ALIGNMENT_METHODS = "mixed_alignment_methods"
    PARTIAL_ALIGNMENT = "partial_alignment"


def _ensure_required_string(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")


def _ensure_enum_member(
    value: object, enum_type: type[Enum], field_name: str, error: type[Exception]
) -> None:
    if not isinstance(value, enum_type):
        raise error(f"{field_name} must be a {enum_type.__name__} member")


def _ensure_finite_non_negative_number(
    value: object, field_name: str, error: type[Exception]
) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error(f"{field_name} must be a number")
    if not math.isfinite(value):
        raise error(f"{field_name} must be finite")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _ensure_ratio(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_finite_non_negative_number(value, field_name, error)
    assert isinstance(value, int | float)
    if value > 1.0:
        raise error(f"{field_name} must be between 0.0 and 1.0")


def _ensure_non_negative_index(value: object, field_name: str, error: type[Exception]) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error(f"{field_name} must be an integer")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _ensure_safe_warning_code(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe warning code")


def _ensure_speaker_label(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not _SPEAKER_LABEL_RE.fullmatch(value):
        raise error(f"{field_name} must match the canonical speaker label format")


@dataclass(frozen=True, slots=True, kw_only=True)
class AlignmentConfig:
    """Stable deterministic configuration for the alignment engine."""

    minimum_overlap_ratio: float = 0.5
    ambiguity_margin: float = 0.1
    word_level_enabled: bool = True
    boundary_tolerance_seconds: float = 0.02

    def __post_init__(self) -> None:
        _ensure_ratio(
            self.minimum_overlap_ratio,
            "minimum_overlap_ratio",
            UnsupportedAlignmentConfigurationError,
        )
        _ensure_ratio(
            self.ambiguity_margin,
            "ambiguity_margin",
            UnsupportedAlignmentConfigurationError,
        )
        if not isinstance(self.word_level_enabled, bool):
            raise UnsupportedAlignmentConfigurationError("word_level_enabled must be a boolean")
        _ensure_finite_non_negative_number(
            self.boundary_tolerance_seconds,
            "boundary_tolerance_seconds",
            UnsupportedAlignmentConfigurationError,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AlignmentRequest:
    """Input contract for deterministic transcript-speaker alignment."""

    call_id: str
    transcription: TranscriptionResult = field(repr=False)
    diarization: DiarizationResult = field(repr=False)
    config: AlignmentConfig = field(default_factory=AlignmentConfig)

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidAlignmentInputError)
        if not isinstance(self.transcription, TranscriptionResult):
            raise InvalidAlignmentInputError("transcription must be a TranscriptionResult")
        if not isinstance(self.diarization, DiarizationResult):
            raise InvalidAlignmentInputError("diarization must be a DiarizationResult")
        if not isinstance(self.config, AlignmentConfig):
            raise InvalidAlignmentInputError("config must be an AlignmentConfig")
        if self.transcription.call_id != self.call_id:
            raise InvalidAlignmentInputError("transcription call_id does not match request call_id")
        if self.diarization.call_id != self.call_id:
            raise InvalidAlignmentInputError("diarization call_id does not match request call_id")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeakerCandidate:
    """Candidate speaker evidence for one aligned transcript unit."""

    speaker_label: str
    overlap_seconds: float
    overlap_ratio: float

    def __post_init__(self) -> None:
        _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidAlignmentResultError)
        _ensure_finite_non_negative_number(
            self.overlap_seconds, "overlap_seconds", InvalidAlignmentResultError
        )
        _ensure_ratio(self.overlap_ratio, "overlap_ratio", InvalidAlignmentResultError)
        if self.overlap_seconds <= 0:
            raise InvalidAlignmentResultError("overlap_seconds must be greater than zero")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeakerAttributedWord:
    """Transcript word annotated with anonymous speaker assignment evidence."""

    source_word_index: int
    text: str = field(repr=False)
    start_seconds: float | None = None
    end_seconds: float | None = None
    speaker_label: str | None = None
    status: AlignmentStatus
    candidates: tuple[SpeakerCandidate, ...] = ()
    overlapping_speech: bool = False

    def __post_init__(self) -> None:
        _ensure_non_negative_index(
            self.source_word_index, "source_word_index", InvalidAlignmentResultError
        )
        _ensure_required_string(self.text, "text", InvalidAlignmentResultError)
        has_start = self.start_seconds is not None
        has_end = self.end_seconds is not None
        if has_start != has_end:
            raise InvalidAlignmentResultError(
                "start_seconds and end_seconds must be provided together"
            )
        if has_start and has_end:
            start = self.start_seconds
            end = self.end_seconds
            if start is None or end is None:
                raise InvalidAlignmentResultError(
                    "timed words require both start_seconds and end_seconds"
                )
            _ensure_finite_non_negative_number(start, "start_seconds", InvalidAlignmentResultError)
            _ensure_finite_non_negative_number(end, "end_seconds", InvalidAlignmentResultError)
            if end < start:
                raise InvalidAlignmentResultError("end_seconds must be >= start_seconds")
        if self.speaker_label is not None:
            _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidAlignmentResultError)
        _ensure_enum_member(self.status, AlignmentStatus, "status", InvalidAlignmentResultError)
        _validate_candidate_list(self.candidates)
        _validate_alignment_outcome(
            status=self.status,
            speaker_label=self.speaker_label,
            candidates=self.candidates,
        )
        if not isinstance(self.overlapping_speech, bool):
            raise InvalidAlignmentResultError("overlapping_speech must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeakerAttributedSegment:
    """Transcript segment annotated with anonymous speaker assignment evidence."""

    source_segment_index: int
    text: str = field(repr=False)
    start_seconds: float
    end_seconds: float
    speaker_label: str | None = None
    status: AlignmentStatus
    alignment_method: AlignmentMethod
    words: tuple[SpeakerAttributedWord, ...] = ()
    candidates: tuple[SpeakerCandidate, ...] = ()
    overlapping_speech: bool = False

    def __post_init__(self) -> None:
        _ensure_non_negative_index(
            self.source_segment_index, "source_segment_index", InvalidAlignmentResultError
        )
        _ensure_required_string(self.text, "text", InvalidAlignmentResultError)
        _ensure_finite_non_negative_number(
            self.start_seconds, "start_seconds", InvalidAlignmentResultError
        )
        _ensure_finite_non_negative_number(
            self.end_seconds, "end_seconds", InvalidAlignmentResultError
        )
        if self.end_seconds < self.start_seconds:
            raise InvalidAlignmentResultError("end_seconds must be >= start_seconds")
        if self.speaker_label is not None:
            _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidAlignmentResultError)
        _ensure_enum_member(self.status, AlignmentStatus, "status", InvalidAlignmentResultError)
        _ensure_enum_member(
            self.alignment_method,
            AlignmentMethod,
            "alignment_method",
            InvalidAlignmentResultError,
        )
        _validate_candidate_list(self.candidates)
        _validate_alignment_outcome(
            status=self.status,
            speaker_label=self.speaker_label,
            candidates=self.candidates,
        )
        if not isinstance(self.overlapping_speech, bool):
            raise InvalidAlignmentResultError("overlapping_speech must be a boolean")

        previous_word_index: int | None = None
        for word in self.words:
            if not isinstance(word, SpeakerAttributedWord):
                raise InvalidAlignmentResultError("words must contain SpeakerAttributedWord values")
            if previous_word_index is not None and word.source_word_index <= previous_word_index:
                raise InvalidAlignmentResultError(
                    "source_word_index values must be strictly increasing"
                )
            previous_word_index = word.source_word_index


@dataclass(frozen=True, slots=True, kw_only=True)
class AlignmentResult:
    """Speaker-labelled transcript alignment result."""

    call_id: str
    segments: tuple[SpeakerAttributedSegment, ...]
    quality_flags: tuple[AlignmentQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidAlignmentResultError)
        for flag in self.quality_flags:
            _ensure_enum_member(
                flag, AlignmentQualityFlag, "quality_flags", InvalidAlignmentResultError
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidAlignmentResultError)

        previous_segment_index: int | None = None
        for segment in self.segments:
            if not isinstance(segment, SpeakerAttributedSegment):
                raise InvalidAlignmentResultError(
                    "segments must contain SpeakerAttributedSegment values"
                )
            if (
                previous_segment_index is not None
                and segment.source_segment_index <= previous_segment_index
            ):
                raise InvalidAlignmentResultError(
                    "source_segment_index values must be strictly increasing"
                )
            previous_segment_index = segment.source_segment_index

        _validate_quality_flags_consistency(self.segments, self.quality_flags)

    @property
    def speaker_labels(self) -> tuple[str, ...]:
        """Sorted unique anonymous speaker labels present in assigned units."""
        labels = {
            label
            for label in (unit.speaker_label for unit in _iter_content_units(self.segments))
            if label is not None
        }
        return tuple(sorted(labels))

    @property
    def assigned_unit_count(self) -> int:
        return sum(
            1
            for unit in _iter_content_units(self.segments)
            if unit.status is AlignmentStatus.ASSIGNED
        )

    @property
    def ambiguous_unit_count(self) -> int:
        return sum(
            1
            for unit in _iter_content_units(self.segments)
            if unit.status is AlignmentStatus.AMBIGUOUS
        )

    @property
    def unassigned_unit_count(self) -> int:
        return sum(
            1
            for unit in _iter_content_units(self.segments)
            if unit.status is AlignmentStatus.UNASSIGNED
        )


def _iter_content_units(
    segments: Sequence[SpeakerAttributedSegment],
) -> Sequence[SpeakerAttributedSegment | SpeakerAttributedWord]:
    units: list[SpeakerAttributedSegment | SpeakerAttributedWord] = []
    for segment in segments:
        if segment.words:
            units.extend(segment.words)
        else:
            units.append(segment)
    return units


def _validate_candidate_list(candidates: Sequence[SpeakerCandidate]) -> None:
    previous_key: tuple[float, float, str] | None = None
    labels: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, SpeakerCandidate):
            raise InvalidAlignmentResultError("candidates must contain SpeakerCandidate values")
        if candidate.speaker_label in labels:
            raise InvalidAlignmentResultError("candidate speaker labels must be unique")
        labels.add(candidate.speaker_label)
        key = (-candidate.overlap_ratio, -candidate.overlap_seconds, candidate.speaker_label)
        if previous_key is not None and key < previous_key:
            raise InvalidAlignmentResultError("candidates must be deterministically ordered")
        previous_key = key


def _validate_alignment_outcome(
    *,
    status: AlignmentStatus,
    speaker_label: str | None,
    candidates: Sequence[SpeakerCandidate],
) -> None:
    if status is AlignmentStatus.ASSIGNED:
        if speaker_label is None:
            raise InvalidAlignmentResultError("assigned status requires a speaker_label")
        if not candidates:
            raise InvalidAlignmentResultError("assigned status requires at least one candidate")
        if candidates[0].speaker_label != speaker_label:
            raise InvalidAlignmentResultError("assigned speaker_label must match top candidate")
    elif status is AlignmentStatus.AMBIGUOUS:
        if speaker_label is not None:
            raise InvalidAlignmentResultError("ambiguous status requires speaker_label to be None")
        if len(candidates) < 2:
            raise InvalidAlignmentResultError("ambiguous status requires at least two candidates")
    elif status is AlignmentStatus.UNASSIGNED and speaker_label is not None:
        raise InvalidAlignmentResultError("unassigned status requires speaker_label to be None")


def _validate_quality_flags_consistency(
    segments: Sequence[SpeakerAttributedSegment],
    quality_flags: Sequence[AlignmentQualityFlag],
) -> None:
    flag_set = set(quality_flags)
    units = list(_iter_content_units(segments))
    assigned_count = sum(1 for unit in units if unit.status is AlignmentStatus.ASSIGNED)
    ambiguous_count = sum(1 for unit in units if unit.status is AlignmentStatus.AMBIGUOUS)
    unassigned_count = sum(1 for unit in units if unit.status is AlignmentStatus.UNASSIGNED)
    has_overlap = any(unit.overlapping_speech for unit in units)
    methods = {segment.alignment_method for segment in segments}

    if not segments:
        if AlignmentQualityFlag.NO_TRANSCRIPT_SPEECH not in flag_set:
            raise InvalidAlignmentResultError(
                "empty segments require NO_TRANSCRIPT_SPEECH quality flag"
            )
        forbidden_when_empty = {
            AlignmentQualityFlag.UNASSIGNED_CONTENT_PRESENT,
            AlignmentQualityFlag.AMBIGUOUS_CONTENT_PRESENT,
            AlignmentQualityFlag.OVERLAPPING_SPEECH_PRESENT,
            AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,
            AlignmentQualityFlag.MIXED_ALIGNMENT_METHODS,
            AlignmentQualityFlag.PARTIAL_ALIGNMENT,
        }
        if forbidden_when_empty & flag_set:
            raise InvalidAlignmentResultError(
                "content quality flags are not valid for empty alignment results"
            )
        return

    if AlignmentQualityFlag.NO_TRANSCRIPT_SPEECH in flag_set:
        raise InvalidAlignmentResultError(
            "NO_TRANSCRIPT_SPEECH cannot be set when aligned segments are present"
        )

    _require_flag_match(
        condition=unassigned_count > 0,
        flag=AlignmentQualityFlag.UNASSIGNED_CONTENT_PRESENT,
        flags=flag_set,
        message="UNASSIGNED_CONTENT_PRESENT must match unassigned content presence",
    )
    _require_flag_match(
        condition=ambiguous_count > 0,
        flag=AlignmentQualityFlag.AMBIGUOUS_CONTENT_PRESENT,
        flags=flag_set,
        message="AMBIGUOUS_CONTENT_PRESENT must match ambiguous content presence",
    )
    _require_flag_match(
        condition=has_overlap,
        flag=AlignmentQualityFlag.OVERLAPPING_SPEECH_PRESENT,
        flags=flag_set,
        message="OVERLAPPING_SPEECH_PRESENT must match overlapping content evidence",
    )
    _require_flag_match(
        condition=AlignmentMethod.SEGMENT_LEVEL in methods,
        flag=AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,
        flags=flag_set,
        message="SEGMENT_LEVEL_FALLBACK_USED must match alignment methods used",
    )
    _require_flag_match(
        condition=len(methods) > 1,
        flag=AlignmentQualityFlag.MIXED_ALIGNMENT_METHODS,
        flags=flag_set,
        message="MIXED_ALIGNMENT_METHODS must match mixed method usage",
    )

    partial_expected = assigned_count > 0 and (ambiguous_count > 0 or unassigned_count > 0)
    _require_flag_match(
        condition=partial_expected,
        flag=AlignmentQualityFlag.PARTIAL_ALIGNMENT,
        flags=flag_set,
        message="PARTIAL_ALIGNMENT must follow its exact consistency rule",
    )


def _require_flag_match(
    *,
    condition: bool,
    flag: AlignmentQualityFlag,
    flags: set[AlignmentQualityFlag],
    message: str,
) -> None:
    has_flag = flag in flags
    if condition != has_flag:
        raise InvalidAlignmentResultError(message)
