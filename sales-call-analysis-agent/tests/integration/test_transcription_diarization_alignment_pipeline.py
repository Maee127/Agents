"""Integration-style alignment pipeline test with synthetic artifacts only."""

from __future__ import annotations

from dataclasses import dataclass

from sales_call_agent.alignment.engine import align_transcript_with_speakers
from sales_call_agent.alignment.models import AlignmentRequest
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.diarization.models import diarization_request_from_normalized_artifact
from sales_call_agent.diarization.provider import run_diarization
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


def test_synthetic_transcription_diarization_alignment_pipeline() -> None:
    artifact = _SyntheticNormalizedArtifact(
        source=_Source(metadata=_Metadata(call_id="call-xyz")),
        normalized_audio=_NormalizedAudio(
            storage_path="normalized/xyz.asr.wav",
            content_hash="xyz",
        ),
    )

    transcription_request = transcription_request_from_normalized_artifact(
        artifact,
        expected_language="en",
        provider_config_id="DEFAULT",
    )
    diarization_request = diarization_request_from_normalized_artifact(
        artifact,
        audio_duration_seconds=4.0,
        provider_config_id="DEFAULT",
    )

    transcription = run_transcription(
        DeterministicFakeTranscriptionProvider(),
        transcription_request,
    )
    diarization = run_diarization(
        DeterministicFakeDiarizationProvider(),
        diarization_request,
    )
    aligned = align_transcript_with_speakers(
        AlignmentRequest(
            call_id="call-xyz",
            transcription=transcription,
            diarization=diarization,
        )
    )

    assert aligned.call_id == "call-xyz"
    assert aligned.segments
    assert aligned.segments[0].text == transcription.segments[0].text
    assert len(aligned.speaker_labels) >= 1
    assert all(label.startswith("SPEAKER_") for label in aligned.speaker_labels)
    rendered = repr(aligned)
    assert "seller" not in rendered.lower()
    assert "customer" not in rendered.lower()
