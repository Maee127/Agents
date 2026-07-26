"""Integration test: canonical normalization using real ffmpeg + ffprobe."""

from __future__ import annotations

import hashlib
import shutil
import wave
from pathlib import Path

import pytest

from sales_call_agent.audio.normalize import normalize_ingested_audio
from sales_call_agent.domain import SourceType
from sales_call_agent.ingestion import ingest_local_file

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and/or ffprobe is not installed",
)


def _write_noncanonical_wav(path: Path, *, seconds: float = 0.6, sample_rate: int = 8000) -> None:
    """Create a stereo 8k WAV, intentionally non-canonical for ASR."""
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00\x00\x00" * frame_count)


def test_normalizes_to_canonical_wav_and_reuses_existing_artifact(tmp_path: Path) -> None:
    source_path = tmp_path / "source-noncanonical.wav"
    _write_noncanonical_wav(source_path)
    original_bytes = source_path.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()

    ingested = ingest_local_file(
        source_path,
        seller_number="+15550000001",
        source_type=SourceType.RECORDER_APP,
    )
    normalized_dir = tmp_path / "normalized"

    first = normalize_ingested_audio(ingested, output_dir=normalized_dir)
    assert first.was_reused is False
    assert first.normalized_properties.channel_count == 1
    assert first.normalized_properties.sample_rate_hz == 16000
    assert first.normalized_properties.codec_name == "pcm_s16le"
    assert "wav" in first.normalized_properties.format_name.lower()
    assert first.normalized_properties.duration_seconds > 0
    assert source_path.read_bytes() == original_bytes

    second = normalize_ingested_audio(ingested, output_dir=normalized_dir)
    assert second.was_reused is True
    assert second.normalized_audio.storage_path == first.normalized_audio.storage_path
    assert second.normalized_content_hash == first.normalized_content_hash
    assert Path(first.normalized_audio.storage_path).name == f"{original_hash}.asr.wav"
