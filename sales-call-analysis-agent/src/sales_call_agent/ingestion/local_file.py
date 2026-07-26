"""Ingest a single local audio file into a validated canonical metadata record.

First vertical slice of Stage 1 ingestion: local files only. No object
storage, no queue, no database, and no audio normalization yet.

The seller parameter is named ``seller_number`` to match the canonical
metadata schema; the ``seller_number`` vs ``seller_id`` question is an open
decision (see ``docs/decisions.md``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sales_call_agent.audio import AudioProperties, InvalidAudioMediaError, probe_audio
from sales_call_agent.domain import AudioAsset, AudioChannels, CallMetadata, SourceType
from sales_call_agent.ingestion.exceptions import (
    CorruptAudioFileError,
    EmptyAudioFileError,
    MissingAudioFileError,
    UnsupportedAudioFormatError,
)

# .3gp/.amr/.mp3 come from the specification's source descriptions; .wav is
# accepted for synthetic test audio and future normalized output.
_SUPPORTED_EXTENSIONS = frozenset({".3gp", ".amr", ".mp3", ".wav"})

_CHANNEL_LAYOUTS = {1: AudioChannels.MONO, 2: AudioChannels.STEREO}


@dataclass(frozen=True, slots=True, kw_only=True)
class IngestionResult:
    """Outcome of ingesting one local audio file."""

    metadata: CallMetadata
    audio: AudioAsset
    properties: AudioProperties

    @property
    def content_hash(self) -> str:
        """SHA-256 hex digest of the ingested file."""
        return self.audio.content_hash


def ingest_local_file(
    filepath: Path | str,
    *,
    seller_number: str,
    source_type: SourceType,
    call_timestamp: datetime | None = None,
) -> IngestionResult:
    """Validate one local audio file and build its canonical metadata record.

    ``call_id`` is derived from the file's SHA-256 (``call-`` plus the first
    16 hex characters), per the specification's "generated or derived hash".
    When ``call_timestamp`` is not given, the file's modification time (UTC)
    is used until source-specific parsers extract real call start times.

    Raises typed domain errors: ``MissingAudioFileError``,
    ``EmptyAudioFileError``, ``UnsupportedAudioFormatError``,
    ``CorruptAudioFileError``, or ``InvalidCallMetadataError``.
    ``AudioProbeUnavailableError`` propagates unchanged when the probe
    tooling itself is unavailable, so an environment failure is never
    mislabeled as a corrupt file. Messages never include the file path or
    filename.

    The path is resolved once; the same absolute path is used for
    validation, hashing, probing, and ``storage_path``.
    """
    path = Path(filepath).resolve()
    if not path.is_file():
        raise MissingAudioFileError("audio file does not exist or is not a regular file")
    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise UnsupportedAudioFormatError("audio file extension is not supported")
    if path.stat().st_size == 0:
        raise EmptyAudioFileError("audio file is empty")

    content_hash = _sha256_of(path)

    try:
        properties = probe_audio(path)
    except InvalidAudioMediaError as error:
        raise CorruptAudioFileError("audio file could not be read as valid audio") from error

    audio_channels = _CHANNEL_LAYOUTS.get(properties.channel_count)
    if audio_channels is None:
        raise UnsupportedAudioFormatError(
            "audio files with more than two channels are not supported"
        )

    if call_timestamp is None:
        call_timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    storage_path = str(path)
    metadata = CallMetadata(
        call_id=f"call-{content_hash[:16]}",
        seller_number=seller_number,
        source_type=source_type,
        call_timestamp=call_timestamp,
        duration_seconds=properties.duration_seconds,
        counterparty_phone=None,
        original_filename=path.name,
        audio_channels=audio_channels,
        storage_path=storage_path,
    )
    audio = AudioAsset(
        storage_path=storage_path,
        audio_channels=audio_channels,
        content_hash=content_hash,
    )
    return IngestionResult(metadata=metadata, audio=audio, properties=properties)


def _sha256_of(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
