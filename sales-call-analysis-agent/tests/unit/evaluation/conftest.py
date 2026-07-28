"""Shared fixtures for evaluation unit tests."""

from __future__ import annotations

import pytest

from sales_call_agent.alignment.models import (
    AlignmentMethod,
    AlignmentQualityFlag,
    AlignmentResult,
    AlignmentStatus,
    SpeakerAttributedSegment,
    SpeakerAttributedWord,
    SpeakerCandidate,
)
from sales_call_agent.evaluation.models import EvaluationRequest, TranscriptEvidenceSpan
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
    RoleAssignmentResult,
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)


@pytest.fixture
def alignment_result() -> AlignmentResult:
    return AlignmentResult(
        call_id="call-eval-1",
        segments=(
            SpeakerAttributedSegment(
                source_segment_index=0,
                text="SECRET_EVAL_SEGMENT_ONE",
                start_seconds=0.0,
                end_seconds=1.0,
                speaker_label="SPEAKER_00",
                status=AlignmentStatus.ASSIGNED,
                alignment_method=AlignmentMethod.SEGMENT_LEVEL,
                words=(
                    SpeakerAttributedWord(
                        source_word_index=0,
                        text="secret",
                        start_seconds=0.0,
                        end_seconds=0.5,
                        speaker_label="SPEAKER_00",
                        status=AlignmentStatus.ASSIGNED,
                        candidates=(
                            SpeakerCandidate(
                                speaker_label="SPEAKER_00",
                                overlap_seconds=0.5,
                                overlap_ratio=1.0,
                            ),
                        ),
                    ),
                    SpeakerAttributedWord(
                        source_word_index=1,
                        text="one",
                        start_seconds=0.5,
                        end_seconds=1.0,
                        speaker_label="SPEAKER_00",
                        status=AlignmentStatus.ASSIGNED,
                        candidates=(
                            SpeakerCandidate(
                                speaker_label="SPEAKER_00",
                                overlap_seconds=0.5,
                                overlap_ratio=1.0,
                            ),
                        ),
                    ),
                ),
                candidates=(
                    SpeakerCandidate(
                        speaker_label="SPEAKER_00",
                        overlap_seconds=1.0,
                        overlap_ratio=1.0,
                    ),
                ),
            ),
            SpeakerAttributedSegment(
                source_segment_index=1,
                text="SECRET_EVAL_SEGMENT_TWO",
                start_seconds=1.0,
                end_seconds=2.0,
                speaker_label="SPEAKER_01",
                status=AlignmentStatus.ASSIGNED,
                alignment_method=AlignmentMethod.SEGMENT_LEVEL,
                words=(
                    SpeakerAttributedWord(
                        source_word_index=0,
                        text="secret",
                        start_seconds=1.0,
                        end_seconds=1.5,
                        speaker_label="SPEAKER_01",
                        status=AlignmentStatus.ASSIGNED,
                        candidates=(
                            SpeakerCandidate(
                                speaker_label="SPEAKER_01",
                                overlap_seconds=0.5,
                                overlap_ratio=1.0,
                            ),
                        ),
                    ),
                    SpeakerAttributedWord(
                        source_word_index=1,
                        text="two",
                        start_seconds=1.5,
                        end_seconds=2.0,
                        speaker_label="SPEAKER_01",
                        status=AlignmentStatus.ASSIGNED,
                        candidates=(
                            SpeakerCandidate(
                                speaker_label="SPEAKER_01",
                                overlap_seconds=0.5,
                                overlap_ratio=1.0,
                            ),
                        ),
                    ),
                ),
                candidates=(
                    SpeakerCandidate(
                        speaker_label="SPEAKER_01",
                        overlap_seconds=1.0,
                        overlap_ratio=1.0,
                    ),
                ),
            ),
        ),
        quality_flags=(AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,),
    )


@pytest.fixture
def role_assignment_result(alignment_result: AlignmentResult) -> RoleAssignmentResult:
    return assign_speaker_roles(
        RoleAssignmentRequest(
            call_id=alignment_result.call_id,
            alignment=alignment_result,
            evidence=(
                RoleEvidence(
                    evidence_id="ev-01",
                    speaker_label="SPEAKER_00",
                    evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                    suggested_role=SpeakerRole.SELLER,
                ),
                RoleEvidence(
                    evidence_id="ev-02",
                    speaker_label="SPEAKER_01",
                    evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                    suggested_role=SpeakerRole.CUSTOMER,
                ),
            ),
        )
    )


@pytest.fixture
def approved_rubric() -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale_eval_001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="not observed"),
            RubricScoreLevel(score=1.0, label="yes", description="observed"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric_eval_001",
        name="SECRET_RUBRIC_EVAL_NAME",
        version="1.0.0",
        description="SECRET_RUBRIC_EVAL_DESC",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion_eval_001",
                name="SECRET_CRITERION_EVAL_ONE",
                definition="SECRET_DEF_ONE",
                positive_guidance="SECRET_POS_ONE",
                negative_guidance="SECRET_NEG_ONE",
                category=RubricCriterionCategory.DISCOVERY,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(
                    transcript_evidence_required=True,
                    timestamp_required=True,
                    minimum_evidence_spans=1,
                    seller_role_required=True,
                    customer_context_required=False,
                    absence_can_be_evidence=False,
                    human_review_required=False,
                ),
            ),
            RubricCriterion(
                criterion_id="criterion_eval_002",
                name="SECRET_CRITERION_EVAL_TWO",
                definition="SECRET_DEF_TWO",
                positive_guidance="SECRET_POS_TWO",
                negative_guidance="SECRET_NEG_TWO",
                category=RubricCriterionCategory.CLOSING,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(
                    transcript_evidence_required=True,
                    timestamp_required=True,
                    minimum_evidence_spans=1,
                    seller_role_required=True,
                    customer_context_required=True,
                    absence_can_be_evidence=True,
                    human_review_required=True,
                ),
            ),
        ),
    )


@pytest.fixture
def evaluation_request(
    alignment_result: AlignmentResult,
    role_assignment_result: RoleAssignmentResult,
    approved_rubric: SalesRubric,
) -> EvaluationRequest:
    return EvaluationRequest(
        call_id="call-eval-1",
        alignment=alignment_result,
        role_assignment=role_assignment_result,
        rubric=approved_rubric,
    )


@pytest.fixture
def seller_span() -> TranscriptEvidenceSpan:
    return TranscriptEvidenceSpan(
        source_segment_index=0,
        source_word_start_index=0,
        source_word_end_index=1,
        speaker_label="SPEAKER_00",
        speaker_role=SpeakerRole.SELLER,
    )


@pytest.fixture
def customer_span() -> TranscriptEvidenceSpan:
    return TranscriptEvidenceSpan(
        source_segment_index=1,
        source_word_start_index=0,
        source_word_end_index=1,
        speaker_label="SPEAKER_01",
        speaker_role=SpeakerRole.CUSTOMER,
    )
