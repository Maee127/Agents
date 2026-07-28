"""Unit tests for diarization domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sales_call_agent.diarization.exceptions import (
    InvalidDiarizationInputError,
    InvalidDiarizationResponseError,
    UnsupportedSpeakerConstraintError,
)
from sales_call_agent.diarization.models import (
    DiarizationConfidenceMetric,
    DiarizationConfidenceScale,
    DiarizationQualityFlag,
    DiarizationRequest,
    DiarizationResult,
    SpeakerTurn,
    diarization_request_from_normalized_artifact,
    has_cross_speaker_overlap,
    validate_turns_within_audio_duration,
)


def _result(
    *,
    turns: tuple[SpeakerTurn, ...],
    quality_flags: tuple[DiarizationQualityFlag, ...],
) -> DiarizationResult:
    return DiarizationResult(
        call_id="call-1",
        turns=turns,
        provider_name="fake",
        model_name="fake_v1",
        quality_flags=quality_flags,
    )


def test_valid_request_and_turn_construction(sample_request: DiarizationRequest) -> None:
    turn = SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=0.5)
    assert turn.speaker_label == "SPEAKER_00"
    assert sample_request.call_id == "call-1"


def test_frozen_immutability() -> None:
    turn = SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=0.5)
    with pytest.raises(FrozenInstanceError):
        turn.start_seconds = 1.0  # type: ignore[misc]


def test_boolean_timestamps_rejected() -> None:
    with pytest.raises(InvalidDiarizationResponseError, match="start_seconds"):
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=True, end_seconds=1.0)  # type: ignore[arg-type]


def test_zero_length_turn_rejected() -> None:
    with pytest.raises(InvalidDiarizationResponseError, match="greater than start"):
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=1.0, end_seconds=1.0)


def test_turns_must_be_non_decreasing() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=1.0, end_seconds=2.0),
        SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=0.5, end_seconds=1.5),
    )
    with pytest.raises(InvalidDiarizationResponseError, match="non-decreasing"):
        _result(turns=turns, quality_flags=())


def test_overlapping_cross_speaker_turns_allowed() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=2.0),
        SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=3.0),
    )
    assert has_cross_speaker_overlap(turns)
    result = _result(
        turns=turns,
        quality_flags=(DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED,),
    )
    assert result.speaker_count == 2


def test_duplicate_turn_rejected() -> None:
    turn = SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0)
    with pytest.raises(InvalidDiarizationResponseError, match="duplicate"):
        _result(turns=(turn, turn), quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,))


def test_no_speech_result_requires_flag() -> None:
    with pytest.raises(InvalidDiarizationResponseError, match="NO_SPEECH_SEGMENTS"):
        _result(turns=(), quality_flags=())


def test_no_speech_result_valid() -> None:
    result = _result(turns=(), quality_flags=(DiarizationQualityFlag.NO_SPEECH_SEGMENTS,))
    assert result.turns == ()
    assert result.speaker_count == 0


def test_non_empty_turns_forbid_no_speech_flag() -> None:
    turns = (SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),)
    with pytest.raises(InvalidDiarizationResponseError, match="cannot be set when turns"):
        _result(
            turns=turns,
            quality_flags=(DiarizationQualityFlag.NO_SPEECH_SEGMENTS,),
        )


def test_single_speaker_flag_required() -> None:
    turns = (SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),)
    with pytest.raises(InvalidDiarizationResponseError, match="SINGLE_SPEAKER_DETECTED"):
        _result(turns=turns, quality_flags=())


def test_single_speaker_flag_consistency() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=1.0, end_seconds=2.0),
    )
    result = _result(
        turns=turns,
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )
    assert result.speaker_count == 1


def test_overlap_flag_required_when_cross_speaker_overlap_exists() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=2.0),
        SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=3.0),
    )
    with pytest.raises(InvalidDiarizationResponseError, match="OVERLAPPING_SPEECH_DETECTED"):
        _result(turns=turns, quality_flags=())


def test_overlap_flag_invalid_without_cross_speaker_overlap() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
        SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
    )
    with pytest.raises(InvalidDiarizationResponseError, match="requires cross-speaker overlap"):
        _result(
            turns=turns,
            quality_flags=(DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED,),
        )


def test_speaker_count_computed_from_turns() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
        SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=2.0, end_seconds=3.0),
    )
    result = _result(turns=turns, quality_flags=())
    assert result.speaker_count == 2


def test_repeated_canonical_labels_accepted() -> None:
    turns = (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=1.0, end_seconds=2.0),
    )
    result = _result(
        turns=turns,
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )
    assert result.speaker_count == 1


def test_three_digit_speaker_label_accepted() -> None:
    turn = SpeakerTurn(speaker_label="SPEAKER_100", start_seconds=0.0, end_seconds=1.0)
    result = _result(
        turns=(turn,),
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )
    assert result.speaker_count == 1


def test_invalid_speaker_label_rejected() -> None:
    with pytest.raises(InvalidDiarizationResponseError, match="canonical speaker label"):
        SpeakerTurn(speaker_label="speaker_a", start_seconds=0.0, end_seconds=1.0)


def test_mixed_exact_and_range_constraints_rejected() -> None:
    with pytest.raises(UnsupportedSpeakerConstraintError, match="cannot be combined"):
        DiarizationRequest(
            call_id="call-1",
            normalized_audio_path="/tmp/x.asr.wav",
            normalized_audio_hash="abc",
            exact_expected_speakers=2,
            min_expected_speakers=2,
        )


def test_range_min_exceeds_max_rejected() -> None:
    with pytest.raises(UnsupportedSpeakerConstraintError, match="must not exceed"):
        DiarizationRequest(
            call_id="call-1",
            normalized_audio_path="/tmp/x.asr.wav",
            normalized_audio_hash="abc",
            min_expected_speakers=3,
            max_expected_speakers=2,
        )


def test_boolean_speaker_constraint_rejected() -> None:
    with pytest.raises(UnsupportedSpeakerConstraintError, match="integer"):
        DiarizationRequest(
            call_id="call-1",
            normalized_audio_path="/tmp/x.asr.wav",
            normalized_audio_hash="abc",
            exact_expected_speakers=True,  # type: ignore[arg-type]
        )


def test_confidence_metric_validation() -> None:
    metric = DiarizationConfidenceMetric(
        name="TURN_CONFIDENCE",
        value=0.5,
        scale=DiarizationConfidenceScale.ZERO_TO_ONE,
        higher_is_better=True,
    )
    assert metric.value == 0.5

    with pytest.raises(InvalidDiarizationResponseError, match=r"between 0\.0 and 1\.0"):
        DiarizationConfidenceMetric(
            name="TURN_CONFIDENCE",
            value=1.5,
            scale=DiarizationConfidenceScale.ZERO_TO_ONE,
        )


def test_request_path_hidden_from_repr(sample_request: DiarizationRequest) -> None:
    rendered = repr(sample_request)
    assert sample_request.normalized_audio_path not in rendered


def test_enum_raw_string_rejected_in_quality_flags() -> None:
    turns = (SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),)
    with pytest.raises(InvalidDiarizationResponseError, match="DiarizationQualityFlag"):
        DiarizationResult(
            call_id="call-1",
            turns=turns,
            provider_name="fake",
            model_name="fake_v1",
            quality_flags=("single_speaker_detected",),  # type: ignore[arg-type]
        )


def test_malformed_normalized_artifact_raises_invalid_input() -> None:
    class _BrokenArtifact:
        pass

    with pytest.raises(InvalidDiarizationInputError, match="missing required fields"):
        diarization_request_from_normalized_artifact(_BrokenArtifact())  # type: ignore[arg-type]


def test_malformed_normalized_artifact_does_not_raise_attribute_error() -> None:
    class _PartialArtifact:
        source = object()

    with pytest.raises(InvalidDiarizationInputError):
        diarization_request_from_normalized_artifact(_PartialArtifact())  # type: ignore[arg-type]


def test_validate_turns_within_audio_duration() -> None:
    turns = (SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),)
    validate_turns_within_audio_duration(turns, 2.0)

    with pytest.raises(InvalidDiarizationResponseError, match="exceeds audio duration"):
        validate_turns_within_audio_duration(turns, 0.5)
