"""Shared fixtures for transcription unit tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sales_call_agent.transcription.models import TranscriptionRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class _Metadata:
    call_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _Source:
    metadata: _Metadata


@dataclass(frozen=True, slots=True, kw_only=True)
class _NormalizedAudio:
    storage_path: str
    content_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SyntheticNormalizedArtifact:
    source: _Source
    normalized_audio: _NormalizedAudio


@pytest.fixture
def transcription_request() -> TranscriptionRequest:
    return TranscriptionRequest(
        call_id="call-abc123",
        normalized_audio_path="normalized/abc123.asr.wav",
        normalized_audio_hash="abc123",
        expected_language="en",
        provider_config_id="DEFAULT",
    )


@pytest.fixture
def synthetic_normalized_artifact() -> SyntheticNormalizedArtifact:
    return SyntheticNormalizedArtifact(
        source=_Source(metadata=_Metadata(call_id="call-abc123")),
        normalized_audio=_NormalizedAudio(
            storage_path="normalized/abc123.asr.wav",
            content_hash="abc123",
        ),
    )
