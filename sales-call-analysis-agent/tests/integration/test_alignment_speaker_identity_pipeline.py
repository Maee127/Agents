"""Integration-style role-assignment test with synthetic artifacts only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sales_call_agent.alignment.engine import align_transcript_with_speakers
from sales_call_agent.alignment.models import AlignmentRequest
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.diarization.models import diarization_request_from_normalized_artifact
from sales_call_agent.diarization.provider import run_diarization
from sales_call_agent.speaker_identity.engine import assign_speaker_roles
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentConfig,
    RoleAssignmentRequest,
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)
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


def test_synthetic_alignment_to_role_assignment_pipeline() -> None:
    artifact = _SyntheticNormalizedArtifact(
        source=_Source(metadata=_Metadata(call_id="call-role")),
        normalized_audio=_NormalizedAudio(
            storage_path="normalized/role.wav",
            content_hash="rolehash",
        ),
    )
    transcription = run_transcription(
        DeterministicFakeTranscriptionProvider(),
        transcription_request_from_normalized_artifact(
            cast(Any, artifact),
            expected_language="en",
            provider_config_id="DEFAULT",
        ),
    )
    diarization = run_diarization(
        DeterministicFakeDiarizationProvider(),
        diarization_request_from_normalized_artifact(
            cast(Any, artifact),
            audio_duration_seconds=4.0,
            provider_config_id="DEFAULT",
        ),
    )
    alignment = align_transcript_with_speakers(
        AlignmentRequest(call_id="call-role", transcription=transcription, diarization=diarization)
    )

    evidence = tuple(
        RoleEvidence(
            evidence_id=f"ev-{index:02d}",
            speaker_label=label,
            evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
            suggested_role=SpeakerRole.SELLER if index == 0 else SpeakerRole.CUSTOMER,
        )
        for index, label in enumerate(alignment.speaker_labels)
    )
    result = assign_speaker_roles(
        RoleAssignmentRequest(
            call_id="call-role",
            alignment=alignment,
            evidence=evidence,
            config=RoleAssignmentConfig(allow_heuristics=False),
        )
    )

    assert result.call_id == "call-role"
    assert (
        tuple(current.speaker_label for current in result.assignments) == alignment.speaker_labels
    )
    assert all(current.role is not SpeakerRole.UNKNOWN for current in result.assignments)
    rendered = repr(result)
    assert "SECRET_TRANSCRIPT" not in rendered
