"""Integration test: ingest a real synthetic WAV file using the actual ffprobe binary.

Skipped automatically when ffprobe is not installed, per the testing
conventions for integration tests.
"""

import hashlib
import shutil
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_call_agent.domain import AudioChannels, SourceType
from sales_call_agent.ingestion import ingest_local_file

pytestmark = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is not installed")


def _write_wav(path: Path, *, seconds: float = 0.5, sample_rate: int = 8000) -> None:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * frame_count)


def test_ingests_synthetic_wav_end_to_end(tmp_path: Path) -> None:
    audio_path = tmp_path / "synthetic-call.wav"
    _write_wav(audio_path)
    timestamp = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)

    result = ingest_local_file(
        audio_path,
        seller_number="+15550000001",
        source_type=SourceType.RECORDER_APP,
        call_timestamp=timestamp,
    )

    assert result.metadata.call_timestamp == timestamp
    assert result.metadata.audio_channels is AudioChannels.MONO
    assert result.properties.sample_rate_hz == 8000
    assert result.properties.channel_count == 1
    assert "wav" in result.properties.format_name
    assert result.properties.duration_seconds == pytest.approx(0.5, abs=0.1)
    assert result.metadata.duration_seconds == result.properties.duration_seconds

    expected_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    assert result.content_hash == expected_hash
    assert result.metadata.call_id == f"call-{expected_hash[:16]}"
