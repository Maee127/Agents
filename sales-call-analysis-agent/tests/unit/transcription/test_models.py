"""Unit tests for provider-independent transcription models."""

from __future__ import annotations

import math

import pytest

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionInputError,
    InvalidTranscriptionResponseError,
)
from sales_call_agent.transcription.models import (
    ConfidenceScale,
    ProviderConfidenceMetric,
    TranscriptionQualityFlag,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegment,
    TranscriptWord,
    transcription_request_from_normalized_artifact,
)


def test_valid_request_construction() -> None:
    request = TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path="normalized/source_hash.asr.wav",
        normalized_audio_hash="source_hash",
        expected_language="en",
        provider_config_id="DEFAULT",
    )

    assert request.call_id == "call-1"
    assert request.expected_language == "en"


def test_request_repr_hides_path() -> None:
    request = TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path="normalized/+15550000002.asr.wav",
        normalized_audio_hash="source_hash",
    )

    rendered = repr(request)
    assert "normalized_audio_path" not in rendered
    assert "15550000002" not in rendered


def test_valid_no_speech_result_is_allowed() -> None:
    result = TranscriptionResult(
        call_id="call-1",
        full_text="",
        segments=(),
        detected_language="en",
        language_confidence=0.99,
        provider_name="fake_asr",
        model_name="fake_model",
        quality_flags=(TranscriptionQualityFlag.NO_SPEECH_DETECTED,),
    )

    assert result.segments == ()
    assert result.full_text == ""


def test_empty_result_without_no_speech_flag_is_rejected() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="NO_SPEECH_DETECTED"):
        TranscriptionResult(
            call_id="call-1",
            full_text="",
            segments=(),
            provider_name="fake_asr",
            model_name="fake_model",
        )


def test_provider_confidence_scale_requires_enum_member() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="scale"):
        ProviderConfidenceMetric(
            name="CONF",
            value=0.5,
            scale="ZERO_TO_ONE",  # type: ignore[arg-type]
        )


def test_raw_string_quality_flag_is_rejected() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="quality_flags"):
        TranscriptionResult(
            call_id="call-1",
            full_text="hello",
            segments=(TranscriptSegment(text="hello", start_seconds=0.0, end_seconds=1.0),),
            provider_name="fake_asr",
            model_name="fake_model",
            quality_flags=("NO_SPEECH_DETECTED",),  # type: ignore[arg-type]
        )


def test_invalid_warning_code_is_rejected() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="warning_codes"):
        TranscriptionResult(
            call_id="call-1",
            full_text="hello",
            segments=(TranscriptSegment(text="hello", start_seconds=0.0, end_seconds=1.0),),
            provider_name="fake_asr",
            model_name="fake_model",
            warning_codes=("provider said bad path C:/tmp/file.wav",),
        )


def test_overlapping_segments_are_allowed_when_start_ordered() -> None:
    segment_a = TranscriptSegment(text="a", start_seconds=0.0, end_seconds=2.0)
    segment_b = TranscriptSegment(text="b", start_seconds=1.0, end_seconds=2.5)

    result = TranscriptionResult(
        call_id="call-1",
        full_text="a b",
        segments=(segment_a, segment_b),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    assert len(result.segments) == 2


def test_mixed_timed_and_untimed_words_are_rejected() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="all timestamped or all untimed"):
        TranscriptSegment(
            text="hello world",
            start_seconds=0.0,
            end_seconds=1.0,
            words=(
                TranscriptWord(text="hello", start_seconds=0.0, end_seconds=0.5),
                TranscriptWord(text="world"),
            ),
        )


def test_word_timestamps_must_stay_inside_segment() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="within the segment"):
        TranscriptSegment(
            text="hello",
            start_seconds=0.0,
            end_seconds=1.0,
            words=(TranscriptWord(text="hello", start_seconds=0.0, end_seconds=1.2),),
        )


@pytest.mark.parametrize("bad_value", [True, False, float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_language_confidence_values_are_rejected(bad_value: object) -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="language_confidence"):
        TranscriptionResult(
            call_id="call-1",
            full_text="hello",
            segments=(TranscriptSegment(text="hello", start_seconds=0.0, end_seconds=1.0),),
            detected_language="en",
            language_confidence=bad_value,  # type: ignore[arg-type]
            provider_name="fake_asr",
            model_name="fake_model",
        )


def test_provider_confidence_value_must_be_finite() -> None:
    with pytest.raises(InvalidTranscriptionResponseError, match="finite"):
        ProviderConfidenceMetric(name="CONF", value=math.nan, scale=ConfidenceScale.UNSPECIFIED)


def test_full_text_hidden_from_repr() -> None:
    result = TranscriptionResult(
        call_id="call-1",
        full_text="secret transcript content",
        segments=(TranscriptSegment(text="secret", start_seconds=0.0, end_seconds=1.0),),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    rendered = repr(result)
    assert "secret transcript content" not in rendered


def test_build_request_from_normalized_artifact_contract(
    synthetic_normalized_artifact: object,
) -> None:
    request = transcription_request_from_normalized_artifact(
        synthetic_normalized_artifact, expected_language="en", provider_config_id="DEFAULT"
    )
    assert request.call_id == "call-abc123"
    assert request.normalized_audio_hash == "abc123"


def test_build_request_from_invalid_normalized_artifact_is_rejected() -> None:
    with pytest.raises(InvalidTranscriptionInputError, match="missing required fields"):
        transcription_request_from_normalized_artifact(object())
