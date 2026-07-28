"""Integration-style diarization boundary test with a synthetic normalized artifact."""

from __future__ import annotations

from dataclasses import dataclass

from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.diarization.models import diarization_request_from_normalized_artifact
from sales_call_agent.diarization.provider import run_diarization


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


def test_synthetic_normalized_artifact_to_fake_diarization_result() -> None:
    artifact = _SyntheticNormalizedArtifact(
        source=_Source(metadata=_Metadata(call_id="call-xyz")),
        normalized_audio=_NormalizedAudio(
            storage_path="normalized/xyz.asr.wav",
            content_hash="xyz",
        ),
    )
    request = diarization_request_from_normalized_artifact(
        artifact,
        audio_duration_seconds=4.0,
        provider_config_id="DEFAULT",
    )
    provider = DeterministicFakeDiarizationProvider()
    result = run_diarization(provider, request)

    assert request.call_id == "call-xyz"
    assert result.call_id == request.call_id
    assert result.provider_name == provider.provider_name
    assert result.model_name == provider.model_name
    assert result.turns
    assert result.speaker_count == 2
    assert result.turns[0].start_seconds <= result.turns[-1].start_seconds
