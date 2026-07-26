"""Unit tests for canonical audio normalization."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sales_call_agent.audio.normalize import (
    AudioConversionFailedError,
    FfmpegTimeoutError,
    FfmpegUnavailableError,
    InvalidNormalizedOutputError,
    normalize_ingested_audio,
)
from sales_call_agent.audio.probe import AudioProbeUnavailableError, AudioProperties
from sales_call_agent.domain import AudioAsset, AudioChannels, CallMetadata, SourceType
from sales_call_agent.ingestion.local_file import IngestionResult

_RUN_TARGET = "sales_call_agent.audio.normalize.subprocess.run"
_PROBE_TARGET = "sales_call_agent.audio.normalize.probe_audio"


def _canonical_properties() -> AudioProperties:
    return AudioProperties(
        duration_seconds=1.2,
        format_name="wav",
        codec_name="pcm_s16le",
        sample_rate_hz=16000,
        channel_count=1,
    )


def _noncanonical_codec_properties() -> AudioProperties:
    return AudioProperties(
        duration_seconds=1.2,
        format_name="wav",
        codec_name="mp3",
        sample_rate_hz=16000,
        channel_count=1,
    )


def _make_ingested(tmp_path: Path, *, filename: str = "+15550000002_source.mp3") -> IngestionResult:
    source_path = tmp_path / filename
    source_bytes = b"input-audio-bytes"
    source_path.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    metadata = CallMetadata(
        call_id=f"call-{source_hash[:16]}",
        seller_number="+15550000001",
        source_type=SourceType.RECORDER_APP,
        call_timestamp=datetime(2026, 7, 27, 8, 0, tzinfo=UTC),
        duration_seconds=1.2,
        counterparty_phone=None,
        original_filename=filename,
        audio_channels=AudioChannels.MONO,
        storage_path=str(source_path.resolve()),
    )
    audio = AudioAsset(
        storage_path=str(source_path.resolve()),
        audio_channels=AudioChannels.MONO,
        content_hash=source_hash,
    )
    properties = AudioProperties(
        duration_seconds=1.2,
        format_name="mp3",
        codec_name="mp3",
        sample_rate_hz=8000,
        channel_count=1,
    )
    return IngestionResult(metadata=metadata, audio=audio, properties=properties)


def test_ffmpeg_writes_to_temp_and_publishes_deterministic_final(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"
    expected_final = output_dir / f"{ingested.content_hash}.asr.wav"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"normalized-bytes")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    def fake_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        return _canonical_properties()

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, fake_probe)

    result = normalize_ingested_audio(ingested, output_dir=output_dir)

    ffmpeg_output_path = Path(calls[0][-1]).resolve()
    assert ffmpeg_output_path.parent == output_dir.resolve()
    assert ffmpeg_output_path != expected_final.resolve()
    assert expected_final.exists()
    assert result.normalized_audio.storage_path == str(expected_final.resolve())
    assert result.was_reused is False
    assert expected_final.name == f"{ingested.content_hash}.asr.wav"


def test_successful_verification_atomically_publishes_final(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"fresh-normalized")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    result = normalize_ingested_audio(ingested, output_dir=output_dir)
    final_path = Path(result.normalized_audio.storage_path)
    assert final_path.read_bytes() == b"fresh-normalized"
    assert not any(final_path.parent.glob("tmp-normalized-*.wav"))


def test_failed_conversion_leaves_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    with pytest.raises(AudioConversionFailedError):
        normalize_ingested_audio(ingested, output_dir=output_dir)

    assert not any(output_dir.glob("tmp-normalized-*.wav"))


def test_failed_verification_leaves_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"normalized-but-wrong")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(
        _PROBE_TARGET, lambda path, executable="ffprobe": _noncanonical_codec_properties()
    )

    with pytest.raises(InvalidNormalizedOutputError):
        normalize_ingested_audio(ingested, output_dir=output_dir)

    assert not any(output_dir.glob("tmp-normalized-*.wav"))


def test_preexisting_invalid_target_not_destroyed_if_regeneration_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"{ingested.content_hash}.asr.wav"
    original_bytes = b"old-invalid-target"
    final_path.write_bytes(original_bytes)

    seen_paths: list[Path] = []

    def fake_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        seen_paths.append(path.resolve())
        return _noncanonical_codec_properties()

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(_PROBE_TARGET, fake_probe)
    monkeypatch.setattr(_RUN_TARGET, fake_run)

    with pytest.raises(AudioConversionFailedError):
        normalize_ingested_audio(ingested, output_dir=output_dir)

    assert final_path.read_bytes() == original_bytes
    assert seen_paths[0] == final_path.resolve()


def test_valid_existing_target_is_reused_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"{ingested.content_hash}.asr.wav"
    final_path.write_bytes(b"already-normalized")

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("ffmpeg must not run when a valid final target exists")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    result = normalize_ingested_audio(ingested, output_dir=output_dir)

    assert result.was_reused is True
    assert result.normalized_audio.storage_path == str(final_path.resolve())


def test_codec_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"bytes")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(
        _PROBE_TARGET, lambda path, executable="ffprobe": _noncanonical_codec_properties()
    )

    with pytest.raises(InvalidNormalizedOutputError, match="canonical"):
        normalize_ingested_audio(ingested, output_dir=output_dir)


def test_unavailable_ffprobe_prevents_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"
    final_path = output_dir / f"{ingested.content_hash}.asr.wav"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).write_bytes(b"bytes")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    def unavailable_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        raise AudioProbeUnavailableError("ffprobe executable was not found")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, unavailable_probe)

    with pytest.raises(AudioProbeUnavailableError, match="executable"):
        normalize_ingested_audio(ingested, output_dir=output_dir)

    assert not final_path.exists()
    assert not any(output_dir.glob("tmp-normalized-*.wav"))


def test_missing_ffmpeg_raises_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ffmpeg not on PATH")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    with pytest.raises(FfmpegUnavailableError, match="executable"):
        normalize_ingested_audio(ingested, output_dir=output_dir)


def test_ffmpeg_timeout_raises_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ingested = _make_ingested(tmp_path)
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=command, timeout=60.0)

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    with pytest.raises(FfmpegTimeoutError, match="timed out"):
        normalize_ingested_audio(ingested, output_dir=output_dir)


def test_exception_messages_hide_paths_and_filenames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path, filename="+15550001234_sensitive.mp3")
    output_dir = tmp_path / "normalized"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    with pytest.raises(AudioConversionFailedError) as excinfo:
        normalize_ingested_audio(ingested, output_dir=output_dir)

    message = str(excinfo.value)
    assert "15550001234" not in message
    assert "sensitive.mp3" not in message
    assert str(tmp_path) not in message


def test_rejects_output_dir_when_it_is_an_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingested = _make_ingested(tmp_path)
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("x")
    monkeypatch.setattr(_RUN_TARGET, lambda command, **kwargs: None)  # pragma: no cover
    monkeypatch.setattr(_PROBE_TARGET, lambda path, executable="ffprobe": _canonical_properties())

    with pytest.raises(InvalidNormalizedOutputError, match="directory is invalid"):
        normalize_ingested_audio(ingested, output_dir=output_file)
