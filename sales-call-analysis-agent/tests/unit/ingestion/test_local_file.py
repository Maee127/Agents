"""Unit tests for local-file ingestion. The ffprobe adapter is mocked."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_call_agent.audio import (
    AudioProbeUnavailableError,
    AudioProperties,
    InvalidAudioMediaError,
)
from sales_call_agent.domain import AudioChannels, InvalidCallMetadataError, SourceType
from sales_call_agent.ingestion import (
    CorruptAudioFileError,
    EmptyAudioFileError,
    MissingAudioFileError,
    UnsupportedAudioFormatError,
    ingest_local_file,
)

_PROBE_TARGET = "sales_call_agent.ingestion.local_file.probe_audio"

FILE_CONTENT = b"synthetic-mp3-bytes"
SELLER_NUMBER = "+15550000001"


def _properties(channel_count: int = 1) -> AudioProperties:
    return AudioProperties(
        duration_seconds=3.5,
        format_name="mp3",
        codec_name="mp3",
        sample_rate_hz=8000,
        channel_count=channel_count,
    )


def _patch_probe(monkeypatch: pytest.MonkeyPatch, properties: AudioProperties) -> None:
    def fake_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        return properties

    monkeypatch.setattr(_PROBE_TARGET, fake_probe)


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "call.mp3"
    path.write_bytes(FILE_CONTENT)
    return path


def test_happy_path_builds_validated_metadata(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    _patch_probe(monkeypatch, _properties())
    timestamp = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)

    result = ingest_local_file(
        audio_file,
        seller_number=SELLER_NUMBER,
        source_type=SourceType.RECORDER_APP,
        call_timestamp=timestamp,
    )

    expected_hash = hashlib.sha256(FILE_CONTENT).hexdigest()
    assert result.content_hash == expected_hash
    assert result.audio.content_hash == expected_hash
    assert result.metadata.call_id == f"call-{expected_hash[:16]}"
    assert result.metadata.seller_number == SELLER_NUMBER
    assert result.metadata.source_type is SourceType.RECORDER_APP
    assert result.metadata.call_timestamp == timestamp
    assert result.metadata.duration_seconds == 3.5
    assert result.metadata.counterparty_phone is None
    assert result.metadata.original_filename == "call.mp3"
    assert result.metadata.audio_channels is AudioChannels.MONO
    assert result.metadata.storage_path == str(audio_file.resolve())
    assert result.audio.storage_path == result.metadata.storage_path
    assert result.properties == _properties()


def test_default_timestamp_uses_file_mtime_in_utc(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    _patch_probe(monkeypatch, _properties())

    result = ingest_local_file(
        audio_file, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP
    )

    expected = datetime.fromtimestamp(audio_file.stat().st_mtime, tz=UTC)
    assert result.metadata.call_timestamp == expected
    assert result.metadata.call_timestamp.tzinfo is UTC


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(MissingAudioFileError):
        ingest_local_file(
            tmp_path / "missing.mp3",
            seller_number=SELLER_NUMBER,
            source_type=SourceType.RECORDER_APP,
        )


def test_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "call.mp3"
    path.write_bytes(b"")

    with pytest.raises(EmptyAudioFileError):
        ingest_local_file(path, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP)


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"not audio")

    with pytest.raises(UnsupportedAudioFormatError):
        ingest_local_file(path, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP)


@pytest.mark.parametrize(
    "probe_message",
    [
        "ffprobe could not read the file as audio media",
        "no audio stream was found in the file",
        "required audio fields are missing or invalid",
    ],
)
def test_invalid_media_maps_to_corrupt_error(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path, probe_message: str
) -> None:
    def failing_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        raise InvalidAudioMediaError(probe_message)

    monkeypatch.setattr(_PROBE_TARGET, failing_probe)

    with pytest.raises(CorruptAudioFileError) as excinfo:
        ingest_local_file(
            audio_file, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP
        )

    assert isinstance(excinfo.value.__cause__, InvalidAudioMediaError)


def test_probe_unavailable_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    def unavailable_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        raise AudioProbeUnavailableError("ffprobe executable was not found")

    monkeypatch.setattr(_PROBE_TARGET, unavailable_probe)

    with pytest.raises(AudioProbeUnavailableError, match="executable"):
        ingest_local_file(
            audio_file, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP
        )


def test_probe_receives_resolved_absolute_path(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    received: list[Path] = []

    def recording_probe(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
        received.append(path)
        return _properties()

    monkeypatch.setattr(_PROBE_TARGET, recording_probe)

    result = ingest_local_file(
        audio_file, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP
    )

    assert received[0].is_absolute()
    assert received[0] == audio_file.resolve()
    assert result.metadata.storage_path == str(received[0])


def test_more_than_two_channels_raises(monkeypatch: pytest.MonkeyPatch, audio_file: Path) -> None:
    _patch_probe(monkeypatch, _properties(channel_count=3))

    with pytest.raises(UnsupportedAudioFormatError, match="two channels"):
        ingest_local_file(
            audio_file, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP
        )


def test_two_channels_map_to_stereo(monkeypatch: pytest.MonkeyPatch, audio_file: Path) -> None:
    _patch_probe(monkeypatch, _properties(channel_count=2))

    result = ingest_local_file(
        audio_file, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP
    )

    assert result.metadata.audio_channels is AudioChannels.STEREO
    assert result.audio.audio_channels is AudioChannels.STEREO


def test_invalid_seller_number_raises_domain_error(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    _patch_probe(monkeypatch, _properties())

    with pytest.raises(InvalidCallMetadataError, match="seller_number"):
        ingest_local_file(audio_file, seller_number="   ", source_type=SourceType.RECORDER_APP)


def test_naive_timestamp_raises_domain_error(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    _patch_probe(monkeypatch, _properties())

    with pytest.raises(InvalidCallMetadataError, match="call_timestamp"):
        ingest_local_file(
            audio_file,
            seller_number=SELLER_NUMBER,
            source_type=SourceType.RECORDER_APP,
            call_timestamp=datetime(2026, 7, 26, 10, 0),
        )


def test_error_messages_do_not_contain_file_path(tmp_path: Path) -> None:
    path = tmp_path / "+15550001234_call.mp3"
    path.write_bytes(b"")

    with pytest.raises(EmptyAudioFileError) as excinfo:
        ingest_local_file(path, seller_number=SELLER_NUMBER, source_type=SourceType.RECORDER_APP)

    message = str(excinfo.value)
    assert "15550001234" not in message
    assert str(tmp_path) not in message
