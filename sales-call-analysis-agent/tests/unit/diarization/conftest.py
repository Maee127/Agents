"""Shared fixtures for diarization unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sales_call_agent.diarization.models import (
    DiarizationRequest,
    SpeakerTurn,
)


@pytest.fixture
def sample_turns() -> tuple[SpeakerTurn, ...]:
    return (
        SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
        SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
    )


@pytest.fixture
def sample_request(tmp_path: Path) -> DiarizationRequest:
    audio_path = tmp_path / "normalized.asr.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")
    return DiarizationRequest(
        call_id="call-1",
        normalized_audio_path=str(audio_path),
        normalized_audio_hash="abc123",
    )
