"""Integration-style transcription boundary test with a synthetic normalized artifact."""

from __future__ import annotations

from dataclasses import dataclass

from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider
from sales_call_agent.transcription.models import transcription_request_from_normalized_artifact
from sales_call_agent.transcription.provider import run_transcription


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
class _SyntheticNormalizedArtifact:
    source: _Source
    normalized_audio: _NormalizedAudio


def test_synthetic_normalized_artifact_to_fake_transcription_result() -> None:
    artifact = _SyntheticNormalizedArtifact(
        source=_Source(metadata=_Metadata(call_id="call-xyz")),
        normalized_audio=_NormalizedAudio(
            storage_path="normalized/xyz.asr.wav",
            content_hash="xyz",
        ),
    )
    request = transcription_request_from_normalized_artifact(
        artifact, expected_language="en", provider_config_id="DEFAULT"
    )
    provider = DeterministicFakeTranscriptionProvider()
    result = run_transcription(provider, request)

    assert request.call_id == "call-xyz"
    assert result.call_id == request.call_id
    assert result.provider_name == provider.provider_name
    assert result.model_name == provider.model_name
    assert result.segments
    assert result.segments[0].start_seconds >= 0
