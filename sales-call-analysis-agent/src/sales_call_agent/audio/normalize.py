"""Canonical ASR normalization for accepted local audio files.

Converts an ingested local file into a canonical ASR-ready format:
WAV container, mono, 16 kHz sample rate, signed 16-bit little-endian PCM.

Safety and privacy guarantees:
- normalization never mutates the original source file;
- FFmpeg writes to a temporary file in the destination directory;
- the temporary file is verified and hashed before atomic publication;
- exception messages never include paths, filenames, phone numbers, stderr,
  or subprocess command contents.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sales_call_agent.audio.probe import (
    AudioProbeUnavailableError,
    AudioProperties,
    probe_audio,
)
from sales_call_agent.domain import AudioAsset, AudioChannels
from sales_call_agent.domain.exceptions import DomainError

if TYPE_CHECKING:
    from sales_call_agent.ingestion.local_file import IngestionResult

_FFMPEG_TIMEOUT_SECONDS = 60.0
_CANONICAL_SAMPLE_RATE_HZ = 16_000
_CANONICAL_CODEC_NAME = "pcm_s16le"
_CANONICAL_CHANNEL_COUNT = 1
_CANONICAL_CONTAINER_TOKEN = "wav"


class AudioNormalizationError(DomainError):
    """Base class for normalization failures. Never raised directly."""


class FfmpegUnavailableError(AudioNormalizationError):
    """Raised when FFmpeg is not available on the host environment."""


class FfmpegTimeoutError(AudioNormalizationError):
    """Raised when FFmpeg conversion exceeds the configured timeout."""


class AudioConversionFailedError(AudioNormalizationError):
    """Raised when FFmpeg exits non-zero during conversion."""


class InvalidNormalizedOutputError(AudioNormalizationError):
    """Raised when normalized output is missing or violates canonical constraints."""


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizedAudioResult:
    """Normalization output for one ingested audio file."""

    source: IngestionResult
    normalized_audio: AudioAsset
    normalized_properties: AudioProperties
    was_reused: bool

    @property
    def normalized_content_hash(self) -> str:
        """SHA-256 hex digest of the normalized artifact."""
        return self.normalized_audio.content_hash


def normalize_ingested_audio(
    ingested: IngestionResult,
    *,
    output_dir: Path | str | None = None,
    ffmpeg_executable: str = "ffmpeg",
    ffprobe_executable: str = "ffprobe",
) -> NormalizedAudioResult:
    """Normalize an already-ingested local file into canonical ASR format.

    The path from ingestion is treated as the source of truth. The deterministic
    final target name is ``<full-source-sha256>.asr.wav``.
    """
    _validate_ingested_contract(ingested)

    source_path = Path(ingested.metadata.storage_path).resolve()
    destination_dir = _resolve_destination_directory(source_path, output_dir)
    final_target = _derive_final_target(destination_dir, ingested.content_hash)

    reusable = _try_reuse_existing(
        ingested=ingested, final_target=final_target, ffprobe_executable=ffprobe_executable
    )
    if reusable is not None:
        return reusable

    temp_target = _create_temp_target(destination_dir)
    try:
        _run_ffmpeg_conversion(
            source_path=source_path,
            temp_target=temp_target,
            ffmpeg_executable=ffmpeg_executable,
        )
        normalized_properties = _verify_canonical_output(
            temp_target, ffprobe_executable=ffprobe_executable
        )
        normalized_hash = _sha256_of(temp_target)
        temp_target.replace(final_target)

        normalized_audio = AudioAsset(
            storage_path=str(final_target),
            audio_channels=AudioChannels.MONO,
            content_hash=normalized_hash,
        )
        return NormalizedAudioResult(
            source=ingested,
            normalized_audio=normalized_audio,
            normalized_properties=normalized_properties,
            was_reused=False,
        )
    except (AudioNormalizationError, AudioProbeUnavailableError):
        _cleanup_temp_file(temp_target)
        raise


def _resolve_destination_directory(source_path: Path, output_dir: Path | str | None) -> Path:
    destination_dir = (
        source_path.parent / "normalized"
        if output_dir is None
        else Path(output_dir).expanduser().resolve()
    )
    if destination_dir.exists() and not destination_dir.is_dir():
        raise InvalidNormalizedOutputError("normalization output directory is invalid")
    destination_dir.mkdir(parents=True, exist_ok=True)
    return destination_dir


def _derive_final_target(destination_dir: Path, source_hash: str) -> Path:
    final_target = (destination_dir / f"{source_hash}.asr.wav").resolve()
    if final_target.parent != destination_dir.resolve():
        raise InvalidNormalizedOutputError("normalization output directory is invalid")
    return final_target


def _try_reuse_existing(
    *,
    ingested: IngestionResult,
    final_target: Path,
    ffprobe_executable: str,
) -> NormalizedAudioResult | None:
    if not final_target.exists():
        return None
    if not final_target.is_file():
        raise InvalidNormalizedOutputError("normalized output path is invalid")

    try:
        properties = _verify_canonical_output(final_target, ffprobe_executable=ffprobe_executable)
    except InvalidNormalizedOutputError:
        # Keep the existing invalid target untouched until a fresh artifact is
        # generated and atomically published.
        return None

    normalized_audio = AudioAsset(
        storage_path=str(final_target),
        audio_channels=AudioChannels.MONO,
        content_hash=_sha256_of(final_target),
    )
    return NormalizedAudioResult(
        source=ingested,
        normalized_audio=normalized_audio,
        normalized_properties=properties,
        was_reused=True,
    )


def _validate_ingested_contract(ingested: object) -> None:
    """Validate only the attributes this module actually requires."""
    metadata = getattr(ingested, "metadata", None)
    content_hash = getattr(ingested, "content_hash", None)
    storage_path = getattr(metadata, "storage_path", None)
    if not isinstance(content_hash, str) or not content_hash:
        raise InvalidNormalizedOutputError("ingested input is invalid")
    if not isinstance(storage_path, str) or not storage_path:
        raise InvalidNormalizedOutputError("ingested input is invalid")


def _create_temp_target(destination_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".wav",
        prefix="tmp-normalized-",
        dir=destination_dir,
        delete=False,
    ) as handle:
        return Path(handle.name).resolve()


def _run_ffmpeg_conversion(
    *,
    source_path: Path,
    temp_target: Path,
    ffmpeg_executable: str,
) -> None:
    command = [
        ffmpeg_executable,
        "-v",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-acodec",
        _CANONICAL_CODEC_NAME,
        "-ac",
        str(_CANONICAL_CHANNEL_COUNT),
        "-ar",
        str(_CANONICAL_SAMPLE_RATE_HZ),
        "-f",
        _CANONICAL_CONTAINER_TOKEN,
        str(temp_target),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise FfmpegUnavailableError("ffmpeg executable was not found") from error
    except subprocess.TimeoutExpired as error:
        raise FfmpegTimeoutError("ffmpeg timed out") from error

    if completed.returncode != 0:
        raise AudioConversionFailedError("ffmpeg conversion failed")


def _verify_canonical_output(path: Path, *, ffprobe_executable: str) -> AudioProperties:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
        raise InvalidNormalizedOutputError("normalized output is missing or empty")

    properties = probe_audio(path, executable=ffprobe_executable)
    format_tokens = {token.strip().lower() for token in properties.format_name.split(",")}
    if _CANONICAL_CONTAINER_TOKEN not in format_tokens:
        raise InvalidNormalizedOutputError("normalized output is not canonical")
    if properties.codec_name.lower() != _CANONICAL_CODEC_NAME:
        raise InvalidNormalizedOutputError("normalized output is not canonical")
    if properties.channel_count != _CANONICAL_CHANNEL_COUNT:
        raise InvalidNormalizedOutputError("normalized output is not canonical")
    if properties.sample_rate_hz != _CANONICAL_SAMPLE_RATE_HZ:
        raise InvalidNormalizedOutputError("normalized output is not canonical")
    if not math.isfinite(properties.duration_seconds) or properties.duration_seconds <= 0:
        raise InvalidNormalizedOutputError("normalized output is not canonical")
    return properties


def _sha256_of(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _cleanup_temp_file(path: Path) -> None:
    # Never replace a primary failure with cleanup noise.
    with suppress(OSError):
        path.unlink(missing_ok=True)
