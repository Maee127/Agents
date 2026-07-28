"""Unit tests for deterministic call-level aggregation engine."""

from __future__ import annotations

import pytest

from sales_call_agent.aggregation.engine import aggregate_call_evaluation
from sales_call_agent.aggregation.exceptions import (
    InvalidAggregationInputError,
    UnsupportedScoringScaleError,
)
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
from sales_call_agent.knowledge.models import RubricScoreLevel, RubricScoringScale
from sales_call_agent.speaker_identity.models import SpeakerRole


def _span(segment_index: int, role: SpeakerRole = SpeakerRole.SELLER) -> TranscriptEvidenceSpan:
    return TranscriptEvidenceSpan(
        source_segment_index=segment_index,
        speaker_label="SPEAKER_00" if role is SpeakerRole.SELLER else "SPEAKER_01",
        speaker_role=role,
    )


def test_all_scored_aggregation(aggregation_request: AggregationRequest) -> None:
    result = aggregate_call_evaluation(aggregation_request)
    assert result.weighted_performance_score is not None
    assert result.scored_weight_coverage == pytest.approx(1.0)
    assert result.scored_criterion_coverage == pytest.approx(1.0)
    assert result.publication_status is CallScorePublicationStatus.HUMAN_REVIEW_REQUIRED
    assert AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC in result.quality_flags


def test_retains_config_policy_snapshot(aggregation_request: AggregationRequest) -> None:
    config = AggregationConfig(
        minimum_scored_weight_coverage=0.95,
        minimum_scored_criterion_coverage=0.95,
        require_no_human_review_for_publish=False,
    )
    request = AggregationRequest(
        call_id=aggregation_request.call_id,
        rubric=aggregation_request.rubric,
        evaluation=aggregation_request.evaluation,
        config=config,
    )
    result = aggregate_call_evaluation(request)
    assert result.config == config
    assert result.publication_status is CallScorePublicationStatus.PUBLISHABLE


def test_same_score_different_thresholds_changes_publication(
    aggregation_request: AggregationRequest,
) -> None:
    base = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=aggregation_request.evaluation,
            config=AggregationConfig(require_no_human_review_for_publish=False),
        )
    )
    strict = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=aggregation_request.evaluation,
            config=AggregationConfig(
                minimum_scored_weight_coverage=1.0,
                minimum_scored_criterion_coverage=1.0,
                require_no_human_review_for_publish=True,
            ),
        )
    )
    assert base.weighted_performance_score == strict.weighted_performance_score
    assert base.publication_status is not strict.publication_status


def test_reason_code_and_human_review_reason_copied_exactly(
    aggregation_request: AggregationRequest,
) -> None:
    result = aggregate_call_evaluation(aggregation_request)
    copied = result.criterion_contributions[1]
    source = aggregation_request.evaluation.criterion_evaluations[1]
    assert copied.reason_code is source.reason_code
    assert copied.human_review_reason is source.human_review_reason


def test_some_scored_some_insufficient(aggregation_request: AggregationRequest) -> None:
    eval_result = CallEvaluationResult(
        call_id=aggregation_request.call_id,
        rubric_id=aggregation_request.rubric.rubric_id,
        rubric_version=aggregation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            aggregation_request.evaluation.criterion_evaluations[0],
            CriterionEvaluation(
                criterion_id="criterion_agg_002",
                status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                reason_code=CriterionEvaluationReason.INSUFFICIENT_EVIDENCE_SPANS,
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
            aggregation_request.evaluation.criterion_evaluations[2],
        ),
        quality_flags=(
            EvaluationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
            EvaluationQualityFlag.PARTIAL_EVALUATION,
        ),
    )
    result = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=eval_result,
            config=AggregationConfig(require_no_human_review_for_publish=False),
        )
    )
    assert result.weighted_performance_score is not None
    assert result.scored_criterion_coverage == pytest.approx(2 / 3)
    assert AggregationQualityFlag.PARTIAL_SCORE in result.quality_flags


def test_fully_scored_with_not_applicable(aggregation_request: AggregationRequest) -> None:
    eval_result = CallEvaluationResult(
        call_id=aggregation_request.call_id,
        rubric_id=aggregation_request.rubric.rubric_id,
        rubric_version=aggregation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            aggregation_request.evaluation.criterion_evaluations[0],
            CriterionEvaluation(
                criterion_id="criterion_agg_002",
                status=CriterionEvaluationStatus.NOT_APPLICABLE,
                reason_code=CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
            aggregation_request.evaluation.criterion_evaluations[2],
        ),
        quality_flags=(
            EvaluationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
            EvaluationQualityFlag.PARTIAL_EVALUATION,
        ),
    )
    result = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=eval_result,
        )
    )
    assert result.scored_criterion_coverage == pytest.approx(1.0)
    assert AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC in result.quality_flags


def test_all_insufficient_behavior(aggregation_request: AggregationRequest) -> None:
    eval_result = CallEvaluationResult(
        call_id=aggregation_request.call_id,
        rubric_id=aggregation_request.rubric.rubric_id,
        rubric_version=aggregation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            CriterionEvaluation(
                criterion_id="criterion_agg_001",
                status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
            ),
            CriterionEvaluation(
                criterion_id="criterion_agg_002",
                status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
            CriterionEvaluation(
                criterion_id="criterion_agg_003",
                status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
            ),
        ),
        quality_flags=(
            EvaluationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
        ),
    )
    result = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=eval_result,
        )
    )
    assert result.weighted_performance_score is None
    assert result.scored_criterion_coverage == pytest.approx(0.0)
    assert result.scored_weight_coverage == pytest.approx(0.0)
    assert result.publication_status is CallScorePublicationStatus.NO_SCORABLE_CRITERIA
    assert AggregationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT in result.quality_flags
    assert AggregationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT not in result.quality_flags


def test_all_not_applicable_behavior(aggregation_request: AggregationRequest) -> None:
    eval_result = CallEvaluationResult(
        call_id=aggregation_request.call_id,
        rubric_id=aggregation_request.rubric.rubric_id,
        rubric_version=aggregation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            CriterionEvaluation(
                criterion_id="criterion_agg_001",
                status=CriterionEvaluationStatus.NOT_APPLICABLE,
                reason_code=CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
            ),
            CriterionEvaluation(
                criterion_id="criterion_agg_002",
                status=CriterionEvaluationStatus.NOT_APPLICABLE,
                reason_code=CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
            CriterionEvaluation(
                criterion_id="criterion_agg_003",
                status=CriterionEvaluationStatus.NOT_APPLICABLE,
                reason_code=CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
            ),
        ),
        quality_flags=(
            EvaluationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
        ),
    )
    result = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=eval_result,
        )
    )
    assert result.weighted_performance_score is None
    assert result.scored_criterion_coverage is None
    assert result.scored_weight_coverage is None
    assert result.publication_status is CallScorePublicationStatus.NO_SCORABLE_CRITERIA
    assert AggregationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT in result.quality_flags
    assert AggregationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT not in result.quality_flags
    assert AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC not in result.quality_flags


def test_threshold_equality_passes(aggregation_request: AggregationRequest) -> None:
    eval_result = CallEvaluationResult(
        call_id=aggregation_request.call_id,
        rubric_id=aggregation_request.rubric.rubric_id,
        rubric_version=aggregation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=(
            aggregation_request.evaluation.criterion_evaluations[0],
            CriterionEvaluation(
                criterion_id="criterion_agg_002",
                status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                reason_code=CriterionEvaluationReason.INSUFFICIENT_EVIDENCE_SPANS,
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
            aggregation_request.evaluation.criterion_evaluations[2],
        ),
        quality_flags=(
            EvaluationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
            EvaluationQualityFlag.PARTIAL_EVALUATION,
        ),
    )
    result = aggregate_call_evaluation(
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=eval_result,
            config=AggregationConfig(
                minimum_scored_weight_coverage=2.0 / 3.0,
                minimum_scored_criterion_coverage=2.0 / 3.0,
                require_no_human_review_for_publish=False,
            ),
        )
    )
    assert AggregationQualityFlag.LIMITED_WEIGHT_COVERAGE not in result.quality_flags
    assert AggregationQualityFlag.LIMITED_CRITERION_COVERAGE not in result.quality_flags
    assert result.publication_status is CallScorePublicationStatus.PUBLISHABLE


def test_single_level_scale_rejected(aggregation_request: AggregationRequest) -> None:
    single_level = RubricScoringScale(
        scale_id="single_level",
        name="single",
        levels=(RubricScoreLevel(score=1.0, label="only", description="only"),),
    )
    criterion = aggregation_request.rubric.criteria[0]
    modified = criterion.__class__(
        criterion_id=criterion.criterion_id,
        name=criterion.name,
        definition=criterion.definition,
        positive_guidance=criterion.positive_guidance,
        negative_guidance=criterion.negative_guidance,
        category=criterion.category,
        origin=criterion.origin,
        weight=criterion.weight,
        scoring_scale=single_level,
        evidence_requirement=criterion.evidence_requirement,
        source_citations=criterion.source_citations,
        warning_codes=criterion.warning_codes,
    )
    rubric = aggregation_request.rubric.__class__(
        rubric_id=aggregation_request.rubric.rubric_id,
        name=aggregation_request.rubric.name,
        version=aggregation_request.rubric.version,
        description=aggregation_request.rubric.description,
        language=aggregation_request.rubric.language,
        status=aggregation_request.rubric.status,
        criteria=(modified, *aggregation_request.rubric.criteria[1:]),
        warning_codes=aggregation_request.rubric.warning_codes,
    )
    with pytest.raises(UnsupportedScoringScaleError):
        aggregate_call_evaluation(
            AggregationRequest(
                call_id=aggregation_request.call_id,
                rubric=rubric,
                evaluation=aggregation_request.evaluation,
            )
        )


def test_request_coverage_mismatch_rejected(aggregation_request: AggregationRequest) -> None:
    bad_eval = CallEvaluationResult(
        call_id=aggregation_request.call_id,
        rubric_id=aggregation_request.rubric.rubric_id,
        rubric_version=aggregation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_model",
        criterion_evaluations=aggregation_request.evaluation.criterion_evaluations[:-1],
        quality_flags=(
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
            EvaluationQualityFlag.ALL_CRITERIA_SCORED,
        ),
    )
    with pytest.raises(InvalidAggregationInputError):
        AggregationRequest(
            call_id=aggregation_request.call_id,
            rubric=aggregation_request.rubric,
            evaluation=bad_eval,
        )


def test_contribution_order_follows_rubric_order(aggregation_request: AggregationRequest) -> None:
    result = aggregate_call_evaluation(aggregation_request)
    assert tuple(item.criterion_id for item in result.criterion_contributions) == tuple(
        criterion.criterion_id for criterion in aggregation_request.rubric.criteria
    )


def test_deterministic_repeated_equality(aggregation_request: AggregationRequest) -> None:
    first = aggregate_call_evaluation(aggregation_request)
    second = aggregate_call_evaluation(aggregation_request)
    assert first == second


def test_repr_does_not_leak_proprietary_text(aggregation_request: AggregationRequest) -> None:
    result = aggregate_call_evaluation(aggregation_request)
    rendered = repr(result)
    assert "SECRET_RUBRIC_AGG" not in rendered
    assert "SECRET_CRITERION_1" not in rendered
