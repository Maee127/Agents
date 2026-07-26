"""Call ingestion: accepting and validating incoming call recordings and metadata."""

from sales_call_agent.ingestion.exceptions import (
    CorruptAudioFileError,
    EmptyAudioFileError,
    IngestionError,
    MissingAudioFileError,
    UnsupportedAudioFormatError,
)
from sales_call_agent.ingestion.local_file import IngestionResult, ingest_local_file

__all__ = [
    "CorruptAudioFileError",
    "EmptyAudioFileError",
    "IngestionError",
    "IngestionResult",
    "MissingAudioFileError",
    "UnsupportedAudioFormatError",
    "ingest_local_file",
]
