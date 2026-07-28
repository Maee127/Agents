"""Unit tests for deterministic transcript-speaker alignment engine."""

from __future__ import annotations

import pytest

from sales_call_agent.alignment.engine import align_transcript_with_speakers
from sales_call_agent.alignment.exceptions import InvalidAlignmentInputError
from sales_call_agent.alignment.models import (
    AlignmentConfig,
    AlignmentMethod,
    AlignmentQualityFlag,
    AlignmentRequest,
    AlignmentStatus,
    SpeakerAttributedWord,
)
from sales_call_agent.diarization.models import (
    DiarizationQualityFlag,
    DiarizationResult,
    SpeakerTurn,
)
from sales_call_agent.transcription.models import (
    TranscriptionQualityFlag,
    TranscriptionResult,
    TranscriptSegment,
    TranscriptWord,
)


def _request(
    transcription: TranscriptionResult,
    diarization: DiarizationResult,
    *,
    config: AlignmentConfig | None = None,
) -> AlignmentRequest:
    return AlignmentRequest(
        call_id=transcription.call_id,
        transcription=transcription,
        diarization=diarization,
        config=config or AlignmentConfig(),
    )


def test_segment_inside_single_speaker_turn(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    result = align_transcript_with_speakers(_request(transcription_result, diarization_result))
    first_word = result.segments[0].words[0]
    assert first_word.status is AlignmentStatus.ASSIGNED
    assert first_word.speaker_label == "SPEAKER_00"


def test_alternating_words_assigned_to_different_speakers(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    result = align_transcript_with_speakers(_request(transcription_result, diarization_result))
    labels = [word.speaker_label for word in result.segments[0].words]
    assert labels == ["SPEAKER_00", "SPEAKER_01"]


def test_word_level_segment_with_two_assigned_speakers_becomes_ambiguous(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    result = align_transcript_with_speakers(_request(transcription_result, diarization_result))
    segment = result.segments[0]
    assert segment.alignment_method is AlignmentMethod.WORD_LEVEL
    assert segment.status is AlignmentStatus.AMBIGUOUS
    assert segment.speaker_label is None


def test_one_assigned_speaker_plus_unassigned_words_keeps_segment_assigned(
    diarization_result: DiarizationResult,
) -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" one two",
        segments=(
            TranscriptSegment(
                text=" one two",
                start_seconds=0.0,
                end_seconds=2.0,
                words=(
                    TranscriptWord(text=" one", start_seconds=0.0, end_seconds=1.0),
                    TranscriptWord(text=" two", start_seconds=1.0, end_seconds=2.0),
                ),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    only_first_speaker = DiarizationResult(
        call_id="call-1",
        turns=(SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )
    config = AlignmentConfig(minimum_overlap_ratio=0.5, ambiguity_margin=0.1)
    result = align_transcript_with_speakers(
        _request(transcription, only_first_speaker, config=config)
    )
    segment = result.segments[0]
    assert segment.status is AlignmentStatus.ASSIGNED
    assert segment.speaker_label == "SPEAKER_00"
    assert AlignmentQualityFlag.UNASSIGNED_CONTENT_PRESENT in result.quality_flags


def test_any_ambiguous_word_makes_segment_ambiguous() -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" tie",
        segments=(
            TranscriptSegment(
                text=" tie",
                start_seconds=0.0,
                end_seconds=1.0,
                words=(TranscriptWord(text=" tie", start_seconds=0.4, end_seconds=0.6),),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    diarization = DiarizationResult(
        call_id="call-1",
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=0.0, end_seconds=1.0),
        ),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED,),
    )
    result = align_transcript_with_speakers(
        _request(transcription, diarization, config=AlignmentConfig(ambiguity_margin=1.0))
    )
    assert result.segments[0].words[0].status is AlignmentStatus.AMBIGUOUS
    assert result.segments[0].status is AlignmentStatus.AMBIGUOUS


def test_segment_level_fallback_when_words_untimed(
    diarization_result: DiarizationResult,
) -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" untimed words",
        segments=(
            TranscriptSegment(
                text=" untimed words",
                start_seconds=0.0,
                end_seconds=1.0,
                words=(TranscriptWord(text=" untimed"), TranscriptWord(text=" words")),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    result = align_transcript_with_speakers(_request(transcription, diarization_result))
    segment = result.segments[0]
    assert segment.alignment_method is AlignmentMethod.SEGMENT_LEVEL
    assert len(segment.words) == 2
    assert all(word.start_seconds is None for word in segment.words)


def test_tolerance_never_produces_ratio_above_one() -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" x",
        segments=(
            TranscriptSegment(
                text=" x",
                start_seconds=0.0,
                end_seconds=1.0,
                words=(TranscriptWord(text=" x", start_seconds=0.0, end_seconds=1.0),),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    diarization = DiarizationResult(
        call_id="call-1",
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=0.5),
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.5, end_seconds=1.0),
        ),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )
    result = align_transcript_with_speakers(
        _request(transcription, diarization, config=AlignmentConfig(boundary_tolerance_seconds=0.5))
    )
    candidates = result.segments[0].words[0].candidates
    assert candidates
    assert all(0.0 <= candidate.overlap_ratio <= 1.0 for candidate in candidates)


def test_assigned_label_equals_top_candidate(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    result = align_transcript_with_speakers(_request(transcription_result, diarization_result))
    word = result.segments[0].words[0]
    assert word.status is AlignmentStatus.ASSIGNED
    assert word.speaker_label == word.candidates[0].speaker_label


def test_weak_second_candidate_does_not_create_ambiguity() -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" x",
        segments=(
            TranscriptSegment(
                text=" x",
                start_seconds=0.0,
                end_seconds=1.0,
                words=(TranscriptWord(text=" x", start_seconds=0.0, end_seconds=1.0),),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    diarization = DiarizationResult(
        call_id="call-1",
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=0.95, end_seconds=1.0),
        ),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED,),
    )
    result = align_transcript_with_speakers(
        _request(transcription, diarization, config=AlignmentConfig(ambiguity_margin=0.1))
    )
    assert result.segments[0].words[0].status is AlignmentStatus.ASSIGNED


def test_weak_top_candidate_remains_unassigned_even_when_close() -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" x",
        segments=(
            TranscriptSegment(
                text=" x",
                start_seconds=0.0,
                end_seconds=1.0,
                words=(TranscriptWord(text=" x", start_seconds=0.0, end_seconds=1.0),),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    diarization = DiarizationResult(
        call_id="call-1",
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=0.2),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=0.2, end_seconds=0.4),
        ),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(),
    )
    result = align_transcript_with_speakers(
        _request(
            transcription,
            diarization,
            config=AlignmentConfig(minimum_overlap_ratio=0.8, ambiguity_margin=1.0),
        )
    )
    word = result.segments[0].words[0]
    assert word.status is AlignmentStatus.UNASSIGNED


def test_overlap_elsewhere_does_not_set_overlap_flag() -> None:
    transcription = TranscriptionResult(
        call_id="call-1",
        full_text=" hello",
        segments=(
            TranscriptSegment(
                text=" hello",
                start_seconds=0.0,
                end_seconds=1.0,
                words=(TranscriptWord(text=" hello", start_seconds=0.0, end_seconds=1.0),),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )
    diarization = DiarizationResult(
        call_id="call-1",
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=5.0, end_seconds=6.0),
            SpeakerTurn(speaker_label="SPEAKER_02", start_seconds=5.2, end_seconds=5.8),
        ),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED,),
    )
    result = align_transcript_with_speakers(_request(transcription, diarization))
    assert AlignmentQualityFlag.OVERLAPPING_SPEECH_PRESENT not in result.quality_flags


def test_empty_behaviors(
    empty_transcription_result: TranscriptionResult,
    empty_diarization_result: DiarizationResult,
    diarization_result: DiarizationResult,
    transcription_result: TranscriptionResult,
) -> None:
    both_empty = align_transcript_with_speakers(
        _request(empty_transcription_result, empty_diarization_result)
    )
    assert both_empty.segments == ()
    assert AlignmentQualityFlag.NO_TRANSCRIPT_SPEECH in both_empty.quality_flags
    assert AlignmentQualityFlag.NO_DIARIZATION_TURNS in both_empty.quality_flags

    transcript_empty = align_transcript_with_speakers(
        _request(empty_transcription_result, diarization_result)
    )
    assert transcript_empty.segments == ()
    assert transcript_empty.quality_flags == (AlignmentQualityFlag.NO_TRANSCRIPT_SPEECH,)

    diarization_empty = align_transcript_with_speakers(
        _request(transcription_result, empty_diarization_result)
    )
    assert diarization_empty.segments
    assert AlignmentQualityFlag.NO_DIARIZATION_TURNS in diarization_empty.quality_flags
    assert AlignmentQualityFlag.UNASSIGNED_CONTENT_PRESENT in diarization_empty.quality_flags


def test_call_id_mismatch_rejected(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    with pytest.raises(InvalidAlignmentInputError, match="call_id"):
        AlignmentRequest(
            call_id="wrong",
            transcription=transcription_result,
            diarization=diarization_result,
        )


def test_contradictory_source_contract_rejected(diarization_result: DiarizationResult) -> None:
    bad_transcription = TranscriptionResult(
        call_id="call-1",
        full_text="bad",
        segments=(TranscriptSegment(text="bad", start_seconds=0.0, end_seconds=1.0),),
        provider_name="fake_asr",
        model_name="fake_model",
        quality_flags=(TranscriptionQualityFlag.NO_SPEECH_DETECTED,),
    )
    with pytest.raises(InvalidAlignmentInputError, match="contradictory"):
        align_transcript_with_speakers(_request(bad_transcription, diarization_result))


def test_repeated_runs_are_equal(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
) -> None:
    request = _request(transcription_result, diarization_result)
    first = align_transcript_with_speakers(request)
    second = align_transcript_with_speakers(request)
    assert first == second


def test_exception_does_not_expose_transcript_text() -> None:
    leaked = "TRANSCRIPT_DO_NOT_LEAK_123"
    bad_segment = TranscriptSegment(
        text=leaked,
        start_seconds=0.0,
        end_seconds=1.0,
    )
    bad_transcription = TranscriptionResult(
        call_id="call-1",
        full_text=leaked,
        segments=(bad_segment,),
        provider_name="fake_asr",
        model_name="fake_model",
        quality_flags=(TranscriptionQualityFlag.NO_SPEECH_DETECTED,),
    )
    diarization = DiarizationResult(
        call_id="call-1",
        turns=(SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )
    with pytest.raises(InvalidAlignmentInputError) as excinfo:
        align_transcript_with_speakers(_request(bad_transcription, diarization))
    assert leaked not in str(excinfo.value)


def test_programming_errors_are_not_broadly_wrapped(
    transcription_result: TranscriptionResult,
    diarization_result: DiarizationResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> tuple[SpeakerAttributedWord, ...]:
        raise KeyError("unexpected-bug")

    monkeypatch.setattr(
        "sales_call_agent.alignment.engine._segment_candidates_from_words",
        explode,
    )
    with pytest.raises(KeyError, match="unexpected-bug"):
        align_transcript_with_speakers(_request(transcription_result, diarization_result))
