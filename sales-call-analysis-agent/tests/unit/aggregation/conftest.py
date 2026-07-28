"""Shared fixtures for aggregation unit tests."""

from __future__ import annotations

import pytest

from sales_call_agent.aggregation.models import AggregationRequest
from sales_call_agent.evaluation.models import (
    CallEvaluationResult,
    CriterionEvaluation,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationQualityFlag,
    HumanReviewReason,
    TranscriptEvidenceSpan,
)
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
from sales_call_agent.speaker_identity.models import SpeakerRole


@pytest.fixture
def rubric() -> SalesRubric:
    binary = RubricScoringScale(
        scale_id="scale_agg_binary",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="not observed"),
            RubricScoreLevel(score=1.0, label="yes", description="observed"),
        ),
    )
    zero_to_two = RubricScoringScale(
        scale_id="scale_agg_0_2",
        name="0-2",
        levels=(
            RubricScoreLevel(score=0.0, label="low", description="low"),
            RubricScoreLevel(score=1.0, label="mid", description="mid"),
            RubricScoreLevel(score=2.0, label="high", description="high"),
        ),
    )
    one_to_five = RubricScoringScale(
        scale_id="scale_agg_1_5",
        name="1-5",
        levels=(
            RubricScoreLevel(score=1.0, label="1", description="1"),
            RubricScoreLevel(score=2.0, label="2", description="2"),
            RubricScoreLevel(score=3.0, label="3", description="3"),
            RubricScoreLevel(score=4.0, label="4", description="4"),
            RubricScoreLevel(score=5.0, label="5", description="5"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric_agg_001",
        name="SECRET_RUBRIC_AGG",
        version="1.0.0",
        description="SECRET_RUBRIC_AGG_DESC",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion_agg_001",
                name="SECRET_CRITERION_1",
                definition="def1",
                positive_guidance="pos1",
                negative_guidance="neg1",
                category=RubricCriterionCategory.DISCOVERY,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=2.0,
                scoring_scale=binary,
                evidence_requirement=EvidenceRequirement(human_review_required=False),
            ),
            RubricCriterion(
                criterion_id="criterion_agg_002",
                name="SECRET_CRITERION_2",
                definition="def2",
                positive_guidance="pos2",
                negative_guidance="neg2",
                category=RubricCriterionCategory.CLOSING,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=zero_to_two,
                evidence_requirement=EvidenceRequirement(human_review_required=True),
            ),
            RubricCriterion(
                criterion_id="criterion_agg_003",
                name="SECRET_CRITERION_3",
                definition="def3",
                positive_guidance="pos3",
                negative_guidance="neg3",
                category=RubricCriterionCategory.QUALIFICATION,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=3.0,
                scoring_scale=one_to_five,
                evidence_requirement=EvidenceRequirement(human_review_required=False),
            ),
        ),
    )


@pytest.fixture
def evaluation_all_scored(rubric: SalesRubric) -> CallEvaluationResult:
    return CallEvaluationResult(
        call_id="call-agg-1",
        rubric_id=rubric.rubric_id,
        rubric_version=rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            CriterionEvaluation(
                criterion_id="criterion_agg_001",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=1.0,
                score_level_label="yes",
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=0,
                        speaker_label="SPEAKER_00",
                        speaker_role=SpeakerRole.SELLER,
                    ),
                ),
            ),
            CriterionEvaluation(
                criterion_id="criterion_agg_002",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=1.0,
                score_level_label="mid",
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=1,
                        speaker_label="SPEAKER_00",
                        speaker_role=SpeakerRole.SELLER,
                    ),
                ),
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
            CriterionEvaluation(
                criterion_id="criterion_agg_003",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=5.0,
                score_level_label="5",
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=2,
                        speaker_label="SPEAKER_01",
                        speaker_role=SpeakerRole.CUSTOMER,
                    ),
                ),
            ),
        ),
        quality_flags=(
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
            EvaluationQualityFlag.ALL_CRITERIA_SCORED,
        ),
    )


@pytest.fixture
def aggregation_request(
    rubric: SalesRubric,
    evaluation_all_scored: CallEvaluationResult,
) -> AggregationRequest:
    return AggregationRequest(
        call_id="call-agg-1",
        rubric=rubric,
        evaluation=evaluation_all_scored,
    )
