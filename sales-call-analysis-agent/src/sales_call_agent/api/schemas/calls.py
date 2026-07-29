"""Call create/read request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import SecretStr, field_validator

from sales_call_agent.api.schemas.common import (
    RequestApiModel,
    StrictApiModel,
    validate_safe_identifier,
)


class CallCreateRequest(RequestApiModel):
    """Request body for POST /api/v1/calls.

    Mapped domain fields
    --------------------
    call_id                     -> CallMetadata.call_id
    seller_number               -> CallMetadata.seller_number  (not returned in responses)
    source_type                 -> CallMetadata.source_type
    call_timestamp              -> CallMetadata.call_timestamp  (timezone-aware, converted to UTC)
    duration_seconds            -> CallMetadata.duration_seconds
    counterparty_phone          -> CallMetadata.counterparty_phone  (not returned in responses)
    original_filename           -> CallMetadata.original_filename  (not returned in responses)
    audio_channels              -> CallMetadata.audio_channels / AudioAsset.audio_channels
    original_audio_storage_ref  -> CallMetadata.storage_path / AudioAsset.storage_path
                                   (SecretStr: never echoed in errors or responses)
    original_audio_content_hash -> AudioAsset.content_hash  (not returned in responses)
    """

    call_id: str
    seller_number: str
    source_type: str
    call_timestamp: datetime
    duration_seconds: float
    counterparty_phone: str | None = None
    original_filename: str
    audio_channels: str
    original_audio_storage_ref: SecretStr
    original_audio_content_hash: str

    @field_validator("call_id")
    @classmethod
    def _validate_call_id(cls, v: str) -> str:
        return validate_safe_identifier(v)


class CallResponse(StrictApiModel):
    """Privacy-safe summary for call create or read responses.

    Omitted domain fields (not returned)
    -------------------------------------
    seller_number          — PII (phone/identifier)
    counterparty_phone     — PII
    original_filename      — may embed phone numbers
    storage_path           — local path / storage ref
    content_hash           — not needed by clients
    call_timestamp         — operational, not returned in v1
    """

    call_id: str
    status: str
    revision: int
    source_type: str
    audio_channels: str
    duration_seconds: float
    has_transcription: bool = False
    has_diarization: bool = False
    has_alignment: bool = False
    has_role_assignment: bool = False
