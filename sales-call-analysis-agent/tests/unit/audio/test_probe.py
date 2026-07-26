"""Unit tests for the ffprobe adapter. All subprocess calls are mocked."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sales_call_agent.audio import (
    AudioProbeError,
    AudioProbeUnavailableError,
    AudioProperties,
    InvalidAudioMediaError,
    probe_audio,
)

_RUN_TARGET = "sales_call_agent.audio.probe.subprocess.run"


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=""
    )


def _valid_payload() -> dict[str, Any]:
    return {
        "format": {"duration": "3.480000", "format_name": "mp3"},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "mp3",
                "sample_rate": "8000",
                "channels": 1,
            }
        ],
    }


def _patch_run(
    monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str]
) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return result

    monkeypatch.setattr(_RUN_TARGET, fake_run)
    return commands


def test_error_categories_share_the_probe_error_base() -> None:
    assert issubclass(AudioProbeUnavailableError, AudioProbeError)
    assert issubclass(InvalidAudioMediaError, AudioProbeError)


def test_parses_valid_ffprobe_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _completed(stdout=json.dumps(_valid_payload())))

    properties = probe_audio(Path("synthetic.mp3"))

    assert properties == AudioProperties(
        duration_seconds=3.48,
        format_name="mp3",
        codec_name="mp3",
        sample_rate_hz=8000,
        channel_count=1,
    )


def test_passes_executable_and_path_to_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = _patch_run(monkeypatch, _completed(stdout=json.dumps(_valid_payload())))

    probe_audio(Path("synthetic.mp3"), executable="C:/tools/ffprobe.exe")

    assert commands[0][0] == "C:/tools/ffprobe.exe"
    assert commands[0][-1] == "synthetic.mp3"


def test_nonzero_exit_code_raises_invalid_media(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _completed(returncode=1))

    with pytest.raises(InvalidAudioMediaError, match="could not read"):
        probe_audio(Path("synthetic.mp3"))


def test_unparsable_output_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _completed(stdout="this is not json"))

    with pytest.raises(AudioProbeUnavailableError, match="unparsable"):
        probe_audio(Path("synthetic.mp3"))


def test_contract_violating_output_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    payload["streams"] = "not-a-list"
    _patch_run(monkeypatch, _completed(stdout=json.dumps(payload)))

    with pytest.raises(AudioProbeUnavailableError, match="tool contract"):
        probe_audio(Path("synthetic.mp3"))


def test_missing_audio_stream_raises_invalid_media(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    payload["streams"] = [{"codec_type": "video"}]
    _patch_run(monkeypatch, _completed(stdout=json.dumps(payload)))

    with pytest.raises(InvalidAudioMediaError, match="no audio stream"):
        probe_audio(Path("synthetic.mp3"))


def test_missing_required_field_raises_invalid_media(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    del payload["streams"][0]["sample_rate"]
    _patch_run(monkeypatch, _completed(stdout=json.dumps(payload)))

    with pytest.raises(InvalidAudioMediaError, match="missing or invalid"):
        probe_audio(Path("synthetic.mp3"))


def test_non_numeric_duration_raises_invalid_media(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    payload["format"]["duration"] = "N/A"
    _patch_run(monkeypatch, _completed(stdout=json.dumps(payload)))

    with pytest.raises(InvalidAudioMediaError, match="missing or invalid"):
        probe_audio(Path("synthetic.mp3"))


def test_missing_executable_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ffprobe not on PATH")

    monkeypatch.setattr(_RUN_TARGET, fake_run)

    with pytest.raises(AudioProbeUnavailableError, match="executable"):
        probe_audio(Path("synthetic.mp3"))


def test_timeout_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=command, timeout=30.0)

    monkeypatch.setattr(_RUN_TARGET, fake_run)

    with pytest.raises(AudioProbeUnavailableError, match="timed out"):
        probe_audio(Path("synthetic.mp3"))


def test_error_messages_contain_no_path_or_command(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _completed(returncode=1))
    path = Path("secret-folder") / "+15550001234_call.mp3"

    with pytest.raises(InvalidAudioMediaError) as excinfo:
        probe_audio(path, executable="C:/tools/ffprobe.exe")

    message = str(excinfo.value)
    assert "15550001234" not in message
    assert "secret-folder" not in message
    assert "C:/tools" not in message


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_seconds": -1.0},
        {"duration_seconds": float("nan")},
        {"format_name": "   "},
        {"codec_name": "   "},
        {"sample_rate_hz": 0},
        {"channel_count": 0},
    ],
)
def test_audio_properties_reject_invalid_values(overrides: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "duration_seconds": 3.48,
        "format_name": "mp3",
        "codec_name": "mp3",
        "sample_rate_hz": 8000,
        "channel_count": 1,
    }
    values.update(overrides)

    with pytest.raises(InvalidAudioMediaError):
        AudioProperties(**values)
