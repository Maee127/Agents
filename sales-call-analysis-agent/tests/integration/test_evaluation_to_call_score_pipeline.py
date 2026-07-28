"""Integration test for criterion-evaluation to call-score aggregation."""

from __future__ import annotations

from sales_call_agent.aggregation.engine import aggregate_call_evaluation
from sales_call_agent.aggregation.models import (
    AggregationConfig,
    AggregationQualityFlag,
    AggregationRequest,
    CallScorePublicationStatus,
)
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


def test_synthetic_evaluation_to_call_score_pipeline() -> None:
    rubric = SalesRubric(
        rubric_id="rubric_pipeline_agg",
        name="SECRET_PIPELINE_RUBRIC",
        version="1.0.0",
        description="SECRET_PIPELINE_RUBRIC_DESC",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion_pipeline_001",
                name="SECRET_PIPELINE_CRITERION_1",
                definition="d1",
                positive_guidance="p1",
                negative_guidance="n1",
                category=RubricCriterionCategory.OPENING,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=RubricScoringScale(
                    scale_id="scale_pipeline_1",
                    name="binary",
                    levels=(
                        RubricScoreLevel(score=0.0, label="no", description="no"),
                        RubricScoreLevel(score=1.0, label="yes", description="yes"),
                    ),
                ),
                evidence_requirement=EvidenceRequirement(),
            ),
            RubricCriterion(
                criterion_id="criterion_pipeline_002",
                name="SECRET_PIPELINE_CRITERION_2",
                definition="d2",
                positive_guidance="p2",
                negative_guidance="n2",
                category=RubricCriterionCategory.CLOSING,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=2.0,
                scoring_scale=RubricScoringScale(
                    scale_id="scale_pipeline_2",
                    name="0-2",
                    levels=(
                        RubricScoreLevel(score=0.0, label="0", description="0"),
                        RubricScoreLevel(score=1.0, label="1", description="1"),
                        RubricScoreLevel(score=2.0, label="2", description="2"),
                    ),
                ),
                evidence_requirement=EvidenceRequirement(human_review_required=True),
            ),
        ),
    )

    evaluation = CallEvaluationResult(
        call_id="call-pipeline-agg",
        rubric_id=rubric.rubric_id,
        rubric_version=rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            CriterionEvaluation(
                criterion_id="criterion_pipeline_001",
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
                criterion_id="criterion_pipeline_002",
                status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                reason_code=CriterionEvaluationReason.INSUFFICIENT_EVIDENCE_SPANS,
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
        ),
        quality_flags=(
            EvaluationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
            EvaluationQualityFlag.PARTIAL_EVALUATION,
        ),
    )

    strict = aggregate_call_evaluation(
        AggregationRequest(
            call_id=evaluation.call_id,
            rubric=rubric,
            evaluation=evaluation,
            config=AggregationConfig(
                minimum_scored_weight_coverage=0.75,
                minimum_scored_criterion_coverage=0.75,
                require_no_human_review_for_publish=True,
            ),
        )
    )
    relaxed = aggregate_call_evaluation(
        AggregationRequest(
            call_id=evaluation.call_id,
            rubric=rubric,
            evaluation=evaluation,
            config=AggregationConfig(
                minimum_scored_weight_coverage=1.0 / 3.0,
                minimum_scored_criterion_coverage=0.50,
                require_no_human_review_for_publish=False,
            ),
        )
    )

    assert strict.weighted_performance_score == relaxed.weighted_performance_score
    assert strict.publication_status is CallScorePublicationStatus.HUMAN_REVIEW_REQUIRED
    assert relaxed.publication_status is CallScorePublicationStatus.PUBLISHABLE
    assert AggregationQualityFlag.HUMAN_REVIEW_REQUIRED in strict.quality_flags
    assert AggregationQualityFlag.HUMAN_REVIEW_REQUIRED in relaxed.quality_flags
