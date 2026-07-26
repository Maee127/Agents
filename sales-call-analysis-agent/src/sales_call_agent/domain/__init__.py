"""Core domain models and business rules.

Must remain free of I/O, database, and framework dependencies.
"""

from sales_call_agent.domain.exceptions import (
    DomainError,
    InvalidAudioAssetError,
    InvalidCallError,
    InvalidCallMetadataError,
    InvalidStatusTransitionError,
)
from sales_call_agent.domain.models import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    SourceType,
)

__all__ = [
    "AudioAsset",
    "AudioChannels",
    "Call",
    "CallMetadata",
    "CallProcessingStatus",
    "DomainError",
    "InvalidAudioAssetError",
    "InvalidCallError",
    "InvalidCallMetadataError",
    "InvalidStatusTransitionError",
    "SourceType",
]
