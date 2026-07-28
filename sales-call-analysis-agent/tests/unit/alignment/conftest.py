"""Shared fixtures for alignment unit tests."""

from __future__ import annotations

import pytest

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


@pytest.fixture
def transcription_result() -> TranscriptionResult:
    return TranscriptionResult(
        call_id="call-1",
        full_text=" hello world",
        segments=(
            TranscriptSegment(
                text=" hello world",
                start_seconds=0.0,
                end_seconds=2.0,
                words=(
                    TranscriptWord(text=" hello", start_seconds=0.0, end_seconds=1.0),
                    TranscriptWord(text=" world", start_seconds=1.0, end_seconds=2.0),
                ),
            ),
        ),
        provider_name="fake_asr",
        model_name="fake_model",
    )


@pytest.fixture
def diarization_result() -> DiarizationResult:
    return DiarizationResult(
        call_id="call-1",
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
        ),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
    )


@pytest.fixture
def empty_transcription_result() -> TranscriptionResult:
    return TranscriptionResult(
        call_id="call-1",
        full_text="",
        segments=(),
        provider_name="fake_asr",
        model_name="fake_model",
        quality_flags=(TranscriptionQualityFlag.NO_SPEECH_DETECTED,),
    )


@pytest.fixture
def empty_diarization_result() -> DiarizationResult:
    return DiarizationResult(
        call_id="call-1",
        turns=(),
        provider_name="fake_diarization",
        model_name="fake_diarization_v1",
        quality_flags=(DiarizationQualityFlag.NO_SPEECH_SEGMENTS,),
    )
