"""ffprobe adapter for reading technical audio file properties.

Technical support for ingestion. No normalization or transcoding happens
here, and no Python dependencies are added: ffprobe is invoked as a
subprocess and must be available on PATH (or passed explicitly).

Failures fall into two operational categories:

- ``AudioProbeUnavailableError`` — the probe tooling/environment failed
  (missing executable, timeout, output violating the tool contract). The
  supplied media file may be perfectly valid.
- ``InvalidAudioMediaError`` — the supplied file cannot be read as valid
  audio media (unreadable file, no audio stream, missing/invalid media
  fields).

Error messages never include the file path, filename, stderr content, or
subprocess command, because filenames can embed phone numbers (PII).
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sales_call_agent.domain.exceptions import DomainError

_FFPROBE_TIMEOUT_SECONDS = 30.0


class AudioProbeError(DomainError):
    """Base class for audio probe failures. Never raised directly."""


class AudioProbeUnavailableError(AudioProbeError):
    """Raised when the probe tooling or environment fails.

    Covers a missing ffprobe executable, a timeout, and output that violates
    the expected tool contract. The media file itself may be valid.
    """


class InvalidAudioMediaError(AudioProbeError):
    """Raised when the supplied file cannot be read as valid audio media."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioProperties:
    """Technical properties of an audio file as reported by ffprobe."""

    duration_seconds: float
    format_name: str
    sample_rate_hz: int
    channel_count: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise InvalidAudioMediaError("duration_seconds must be a finite, non-negative number")
        if not self.format_name.strip():
            raise InvalidAudioMediaError("format_name must not be empty")
        if self.sample_rate_hz <= 0:
            raise InvalidAudioMediaError("sample_rate_hz must be positive")
        if self.channel_count <= 0:
            raise InvalidAudioMediaError("channel_count must be positive")


def probe_audio(path: Path, *, executable: str = "ffprobe") -> AudioProperties:
    """Read duration, container format, sample rate, and channel count via ffprobe.

    Raises ``AudioProbeUnavailableError`` when the tooling/environment fails
    and ``InvalidAudioMediaError`` when the file cannot be read as valid
    audio media.
    """
    command = [
        executable,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise AudioProbeUnavailableError("ffprobe executable was not found") from error
    except subprocess.TimeoutExpired as error:
        raise AudioProbeUnavailableError("ffprobe timed out") from error

    if completed.returncode != 0:
        raise InvalidAudioMediaError("ffprobe could not read the file as audio media")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AudioProbeUnavailableError("ffprobe produced unparsable output") from error

    return _parse_probe_payload(payload)


def _parse_probe_payload(payload: object) -> AudioProperties:
    if not isinstance(payload, dict):
        raise AudioProbeUnavailableError("ffprobe output was not a JSON object")

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise AudioProbeUnavailableError("ffprobe output violates the expected tool contract")
    audio_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise InvalidAudioMediaError("no audio stream was found in the file")
    stream = audio_streams[0]

    file_format = payload.get("format")
    if not isinstance(file_format, dict):
        raise AudioProbeUnavailableError("ffprobe output contains no format section")

    try:
        return AudioProperties(
            duration_seconds=float(file_format["duration"]),
            format_name=str(file_format["format_name"]),
            sample_rate_hz=int(stream["sample_rate"]),
            channel_count=int(stream["channels"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidAudioMediaError("required audio fields are missing or invalid") from error
