"""Integration-style deterministic role-labelled call evaluation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sales_call_agent.alignment.engine import align_transcript_with_speakers
from sales_call_agent.alignment.models import AlignmentRequest
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.diarization.models import diarization_request_from_normalized_artifact
from sales_call_agent.diarization.provider import run_diarization
from sales_call_agent.evaluation.fake import (
    DeterministicFakeEvaluationProvider,
    FakeCriterionOutcome,
)
from sales_call_agent.evaluation.models import (
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationRequest,
    HumanReviewReason,
    TranscriptEvidenceSpan,
)
from sales_call_agent.evaluation.provider import run_evaluation
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    RubricCriterion,
    RubricCriterionCategory,
    RubricScoreLevel,
    RubricScoringScale,
    RubricStatus,
    SalesRubric,
)
from sales_call_agent.speaker_identity.engine import assign_speaker_roles
from sales_call_agent.speaker_identity.models import (
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


def test_synthetic_role_labelled_call_evaluation_pipeline() -> None:
    artifact = _SyntheticNormalizedArtifact(
        source=_Source(metadata=_Metadata(call_id="call-e2e-eval")),
        normalized_audio=_NormalizedAudio(
            storage_path="normalized/e2e_eval.wav",
            content_hash="e2e_eval_hash",
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
        AlignmentRequest(
            call_id="call-e2e-eval",
            transcription=transcription,
            diarization=diarization,
        )
    )
    role_result = assign_speaker_roles(
        RoleAssignmentRequest(
            call_id="call-e2e-eval",
            alignment=alignment,
            evidence=tuple(
                RoleEvidence(
                    evidence_id=f"ev-{index:02d}",
                    speaker_label=label,
                    evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                    suggested_role=SpeakerRole.SELLER if index == 0 else SpeakerRole.CUSTOMER,
                )
                for index, label in enumerate(alignment.speaker_labels)
            ),
        )
    )
    has_customer_label = len(alignment.speaker_labels) > 1

    scale = RubricScoringScale(
        scale_id="scale_eval_101",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="not observed"),
            RubricScoreLevel(score=1.0, label="yes", description="observed"),
        ),
    )
    rubric = SalesRubric(
        rubric_id="rubric_eval_101",
        name="SECRET_RUBRIC_NAME_E2E",
        version="1.0.0",
        description="SECRET_RUBRIC_DESC_E2E",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion_eval_101",
                name="SECRET_CRITERION_E2E_ONE",
                definition="SECRET_DEF_E2E_ONE",
                positive_guidance="SECRET_POS_E2E_ONE",
                negative_guidance="SECRET_NEG_E2E_ONE",
                category=RubricCriterionCategory.DISCOVERY,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(
                    seller_role_required=True,
                    customer_context_required=False,
                    human_review_required=False,
                ),
            ),
            RubricCriterion(
                criterion_id="criterion_eval_102",
                name="SECRET_CRITERION_E2E_TWO",
                definition="SECRET_DEF_E2E_TWO",
                positive_guidance="SECRET_POS_E2E_TWO",
                negative_guidance="SECRET_NEG_E2E_TWO",
                category=RubricCriterionCategory.CLOSING,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(
                    seller_role_required=True,
                    customer_context_required=has_customer_label,
                    human_review_required=True,
                ),
            ),
        ),
    )
    request = EvaluationRequest(
        call_id="call-e2e-eval",
        alignment=alignment,
        role_assignment=role_result,
        rubric=rubric,
    )
    provider = DeterministicFakeEvaluationProvider(
        outcomes={
            "criterion_eval_101": FakeCriterionOutcome(
                criterion_id="criterion_eval_101",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=0,
                        speaker_label=alignment.speaker_labels[0],
                        speaker_role=SpeakerRole.SELLER,
                    ),
                ),
            ),
            "criterion_eval_102": FakeCriterionOutcome(
                criterion_id="criterion_eval_102",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                evidence_spans=(
                    (
                        TranscriptEvidenceSpan(
                            source_segment_index=0,
                            speaker_label=alignment.speaker_labels[0],
                            speaker_role=SpeakerRole.SELLER,
                        ),
                        TranscriptEvidenceSpan(
                            source_segment_index=1,
                            speaker_label=alignment.speaker_labels[1],
                            speaker_role=SpeakerRole.CUSTOMER,
                        ),
                    )
                    if has_customer_label
                    else (
                        TranscriptEvidenceSpan(
                            source_segment_index=0,
                            speaker_label=alignment.speaker_labels[0],
                            speaker_role=SpeakerRole.SELLER,
                        ),
                    )
                ),
                human_review_required=True,
                human_review_reason=(HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW),
            ),
        }
    )
    result_a = run_evaluation(provider, request)
    result_b = run_evaluation(provider, request)

    assert result_a == result_b
    assert result_a.call_id == "call-e2e-eval"
    assert result_a.rubric_id == "rubric_eval_101"
    assert result_a.rubric_version == "1.0.0"
    assert tuple(item.criterion_id for item in result_a.criterion_evaluations) == (
        "criterion_eval_101",
        "criterion_eval_102",
    )
    assert any(
        span.speaker_role is SpeakerRole.SELLER
        for item in result_a.criterion_evaluations
        for span in item.evidence_spans
    )
    if has_customer_label:
        assert any(
            span.speaker_role is SpeakerRole.CUSTOMER
            for item in result_a.criterion_evaluations
            for span in item.evidence_spans
        )
    assert all(item.score in (0.0, 1.0) for item in result_a.criterion_evaluations)
    rendered = repr(result_a)
    assert "SECRET_RUBRIC_NAME_E2E" not in rendered
    assert "SECRET_POS_E2E_ONE" not in rendered
