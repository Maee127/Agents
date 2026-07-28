"""Opt-in slow integration test for a locally available faster-whisper model.

Skipped unless all of the following are true:
- RUN_LOCAL_ASR_TESTS=1
- faster-whisper is installed
- the configured small model is already available locally
- local_files_only=True (enforced below; no downloads)
"""

from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest

from sales_call_agent.transcription.models import TranscriptionRequest
from sales_call_agent.transcription.provider import run_transcription

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("RUN_LOCAL_ASR_TESTS") != "1",
        reason="set RUN_LOCAL_ASR_TESTS=1 to run local ASR integration tests",
    ),
]


def _faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _write_short_wav(path: Path, *, seconds: float = 0.4, sample_rate: int = 16000) -> None:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * frame_count)


@pytest.mark.skipif(not _faster_whisper_available(), reason="faster-whisper is not installed")
def test_local_tiny_model_returns_structurally_valid_result(tmp_path: Path) -> None:
    from sales_call_agent.transcription.exceptions import TranscriptionProviderUnavailableError
    from sales_call_agent.transcription.models import TranscriptionQualityFlag
    from sales_call_agent.transcription.providers.faster_whisper import (
        FasterWhisperConfig,
        FasterWhisperTranscriptionProvider,
    )

    audio_path = tmp_path / "canonical.asr.wav"
    _write_short_wav(audio_path)
    config = FasterWhisperConfig(
        model_size_or_path="tiny",
        device="cpu",
        compute_type="int8",
        local_files_only=True,
        word_timestamps=True,
    )
    provider = FasterWhisperTranscriptionProvider(config)
    request = TranscriptionRequest(
        call_id="call-local-asr",
        normalized_audio_path=str(audio_path),
        normalized_audio_hash="fixture",
        expected_language="en",
    )

    try:
        result = run_transcription(provider, request)
    except TranscriptionProviderUnavailableError:
        pytest.skip("local tiny model unavailable")

    assert result.call_id == request.call_id
    assert result.provider_name == provider.provider_name
    assert result.model_name == provider.model_name
    assert isinstance(result.full_text, str)
    assert result.processing_duration_seconds is None or result.processing_duration_seconds >= 0
    if result.segments:
        assert result.segments[0].start_seconds <= result.segments[0].end_seconds
    else:
        assert TranscriptionQualityFlag.NO_SPEECH_DETECTED in result.quality_flags
