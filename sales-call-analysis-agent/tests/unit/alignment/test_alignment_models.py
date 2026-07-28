"""Unit tests for alignment models and validation rules."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sales_call_agent.alignment.exceptions import (
    InvalidAlignmentInputError,
    InvalidAlignmentResultError,
    UnsupportedAlignmentConfigurationError,
)
from sales_call_agent.alignment.models import (
    AlignmentConfig,
    AlignmentMethod,
    AlignmentQualityFlag,
    AlignmentRequest,
    AlignmentResult,
    AlignmentStatus,
    SpeakerAttributedSegment,
    SpeakerAttributedWord,
    SpeakerCandidate,
)
from sales_call_agent.diarization.models import DiarizationResult
from sales_call_agent.transcription.models import TranscriptionResult


def _segment(
    *,
    index: int = 0,
    text: str = " secret segment text ",
    speaker_label: str | None = None,
    status: AlignmentStatus = AlignmentStatus.UNASSIGNED,
    method: AlignmentMethod = AlignmentMethod.SEGMENT_LEVEL,
    candidates: tuple[SpeakerCandidate, ...] = (),
    words: tuple[SpeakerAttributedWord, ...] = (),
    overlap: bool = False,
) -> SpeakerAttributedSegment:
    return SpeakerAttributedSegment(
        source_segment_index=index,
        text=text,
        start_seconds=0.0 + index,
        end_seconds=1.0 + index,
        speaker_label=speaker_label,
        status=status,
        alignment_method=method,
        words=words,
        candidates=candidates,
        overlapping_speech=overlap,
    )


def _candidate(label: str, seconds: float, ratio: float) -> SpeakerCandidate:
    return SpeakerCandidate(speaker_label=label, overlap_seconds=seconds, overlap_ratio=ratio)


def test_config_defaults_are_valid() -> None:
    config = AlignmentConfig()
    assert config.minimum_overlap_ratio == 0.5


@pytest.mark.parametrize("value", [True, False, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_config_ratio_rejected(value: object) -> None:
    with pytest.raises(UnsupportedAlignmentConfigurationError):
        AlignmentConfig(minimum_overlap_ratio=value)  # type: ignore[arg-type]


def test_config_boolean_for_numeric_rejected() -> None:
    with pytest.raises(UnsupportedAlignmentConfigurationError):
        AlignmentConfig(boundary_tolerance_seconds=True)  # type: ignore[arg-type]


def test_config_is_frozen() -> None:
    config = AlignmentConfig()
    with pytest.raises(FrozenInstanceError):
        config.minimum_overlap_ratio = 0.2  # type: ignore[misc]


def test_candidate_validation_and_ordering() -> None:
    first = _candidate("SPEAKER_00", 0.5, 0.5)
    second = _candidate("SPEAKER_01", 0.2, 0.2)
    segment = _segment(
        status=AlignmentStatus.AMBIGUOUS,
        candidates=(first, second),
    )
    assert len(segment.candidates) == 2


def test_duplicate_candidates_rejected() -> None:
    candidate = _candidate("SPEAKER_00", 0.5, 0.5)
    with pytest.raises(InvalidAlignmentResultError, match="unique"):
        _segment(
            status=AlignmentStatus.AMBIGUOUS,
            candidates=(candidate, candidate),
        )


def test_assigned_requires_top_candidate_match() -> None:
    with pytest.raises(InvalidAlignmentResultError, match="top candidate"):
        _segment(
            status=AlignmentStatus.ASSIGNED,
            speaker_label="SPEAKER_01",
            candidates=(
                _candidate("SPEAKER_00", 0.8, 0.8),
                _candidate("SPEAKER_01", 0.2, 0.2),
            ),
        )


def test_ambiguous_requires_two_candidates() -> None:
    with pytest.raises(InvalidAlignmentResultError, match="at least two"):
        _segment(
            status=AlignmentStatus.AMBIGUOUS,
            speaker_label=None,
            candidates=(_candidate("SPEAKER_00", 0.5, 0.5),),
        )


def test_unassigned_allows_empty_or_weak_candidates() -> None:
    a = _segment(status=AlignmentStatus.UNASSIGNED, candidates=())
    b = _segment(
        status=AlignmentStatus.UNASSIGNED,
        candidates=(_candidate("SPEAKER_00", 0.1, 0.1),),
    )
    assert a.status is AlignmentStatus.UNASSIGNED
    assert b.status is AlignmentStatus.UNASSIGNED


def test_word_and_segment_text_hidden_from_repr() -> None:
    word = SpeakerAttributedWord(
        source_word_index=0,
        text="VERY_SECRET_WORD",
        speaker_label=None,
        status=AlignmentStatus.UNASSIGNED,
    )
    segment = _segment(text="VERY_SECRET_SEGMENT", words=(word,))
    assert "VERY_SECRET_WORD" not in repr(word)
    assert "VERY_SECRET_SEGMENT" not in repr(segment)


def test_alignment_request_hides_source_objects_in_repr(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    request = AlignmentRequest(
        call_id="call-1",
        transcription=transcription_result,
        diarization=diarization_result,
    )
    rendered = repr(request)
    assert "hello world" not in rendered
    assert "SPEAKER_00" not in rendered
    assert "call-1" in rendered


def test_alignment_request_call_id_mismatch_rejected(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    with pytest.raises(InvalidAlignmentInputError, match="transcription call_id"):
        AlignmentRequest(
            call_id="call-x",
            transcription=transcription_result,
            diarization=diarization_result,
        )


def test_result_counts_and_speaker_labels_computed() -> None:
    assigned = _segment(
        index=0,
        status=AlignmentStatus.ASSIGNED,
        speaker_label="SPEAKER_00",
        candidates=(_candidate("SPEAKER_00", 1.0, 1.0),),
    )
    ambiguous = _segment(
        index=1,
        status=AlignmentStatus.AMBIGUOUS,
        candidates=(
            _candidate("SPEAKER_00", 0.5, 0.5),
            _candidate("SPEAKER_01", 0.5, 0.5),
        ),
    )
    result = AlignmentResult(
        call_id="call-1",
        segments=(assigned, ambiguous),
        quality_flags=(
            AlignmentQualityFlag.AMBIGUOUS_CONTENT_PRESENT,
            AlignmentQualityFlag.PARTIAL_ALIGNMENT,
            AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,
        ),
    )
    assert result.assigned_unit_count == 1
    assert result.ambiguous_unit_count == 1
    assert result.unassigned_unit_count == 0
    assert result.speaker_labels == ("SPEAKER_00",)


def test_partial_alignment_exact_consistency() -> None:
    all_assigned = _segment(
        status=AlignmentStatus.ASSIGNED,
        speaker_label="SPEAKER_00",
        candidates=(_candidate("SPEAKER_00", 1.0, 1.0),),
    )
    with pytest.raises(InvalidAlignmentResultError, match="PARTIAL_ALIGNMENT"):
        AlignmentResult(
            call_id="call-1",
            segments=(all_assigned,),
            quality_flags=(
                AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,
                AlignmentQualityFlag.PARTIAL_ALIGNMENT,
            ),
        )


def test_no_processing_duration_field_present() -> None:
    result = AlignmentResult(
        call_id="call-1",
        segments=(
            _segment(
                status=AlignmentStatus.UNASSIGNED,
                candidates=(),
            ),
        ),
        quality_flags=(
            AlignmentQualityFlag.UNASSIGNED_CONTENT_PRESENT,
            AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,
        ),
    )
    assert not hasattr(result, "processing_duration_seconds")
