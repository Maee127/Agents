"""Unit tests for aggregation models and invariants."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sales_call_agent.aggregation.exceptions import (
    InvalidAggregationInputError,
    InvalidCallScoreResultError,
    InvalidCriterionContributionError,
)
from sales_call_agent.aggregation.models import (
    AggregationConfig,
    AggregationQualityFlag,
    CallScorePublicationStatus,
    CallScoreResult,
    CriterionScoreContribution,
)
from sales_call_agent.evaluation.models import (
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    HumanReviewReason,
)


def test_config_validation() -> None:
    with pytest.raises(InvalidAggregationInputError):
        AggregationConfig(minimum_scored_weight_coverage=1.1)
    with pytest.raises(InvalidAggregationInputError):
        AggregationConfig(minimum_scored_criterion_coverage=-0.1)
    with pytest.raises(InvalidAggregationInputError):
        AggregationConfig(minimum_scored_weight_coverage=True)  # type: ignore[arg-type]


def test_contribution_human_review_consistency() -> None:
    with pytest.raises(InvalidCriterionContributionError):
        CriterionScoreContribution(
            criterion_id="criterion_agg_001",
            status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
            criterion_weight=1.0,
            raw_score=None,
            normalized_score=None,
            weighted_points=None,
            human_review_required=True,
            human_review_reason=None,
            reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
        )


def test_scored_contribution_requires_numeric_fields() -> None:
    with pytest.raises(InvalidCriterionContributionError):
        CriterionScoreContribution(
            criterion_id="criterion_agg_001",
            status=CriterionEvaluationStatus.SCORED,
            criterion_weight=1.0,
            raw_score=1.0,
            normalized_score=None,
            weighted_points=1.0,
            human_review_required=False,
            human_review_reason=None,
            reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
        )


def test_zero_score_distinct_from_none() -> None:
    contribution = CriterionScoreContribution(
        criterion_id="criterion_agg_001",
        status=CriterionEvaluationStatus.SCORED,
        criterion_weight=2.0,
        raw_score=0.0,
        normalized_score=0.0,
        weighted_points=0.0,
        human_review_required=False,
        human_review_reason=None,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
    )
    result = CallScoreResult(
        call_id="call-agg-1",
        rubric_id="rubric_agg_001",
        rubric_version="1.0.0",
        config=AggregationConfig(),
        criterion_contributions=(contribution,),
        weighted_performance_score=0.0,
        scored_weight_coverage=1.0,
        scored_criterion_coverage=1.0,
        publication_status=CallScorePublicationStatus.PUBLISHABLE,
        quality_flags=(
            AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC,
            AggregationQualityFlag.ZERO_PERFORMANCE_SCORE,
        ),
    )
    assert result.has_numeric_score
    assert result.weighted_performance_score == 0.0


def test_result_uses_config_for_status_consistency() -> None:
    contribution = CriterionScoreContribution(
        criterion_id="criterion_agg_001",
        status=CriterionEvaluationStatus.SCORED,
        criterion_weight=1.0,
        raw_score=1.0,
        normalized_score=1.0,
        weighted_points=1.0,
        human_review_required=True,
        human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
    )
    with pytest.raises(InvalidCallScoreResultError):
        CallScoreResult(
            call_id="call-agg-1",
            rubric_id="rubric_agg_001",
            rubric_version="1.0.0",
            config=AggregationConfig(require_no_human_review_for_publish=True),
            criterion_contributions=(contribution,),
            weighted_performance_score=1.0,
            scored_weight_coverage=1.0,
            scored_criterion_coverage=1.0,
            publication_status=CallScorePublicationStatus.PUBLISHABLE,
            quality_flags=(
                AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC,
                AggregationQualityFlag.HUMAN_REVIEW_REQUIRED,
            ),
        )


def test_result_is_frozen() -> None:
    result = CallScoreResult(
        call_id="call-agg-1",
        rubric_id="rubric_agg_001",
        rubric_version="1.0.0",
        config=AggregationConfig(),
        criterion_contributions=(),
        weighted_performance_score=None,
        scored_weight_coverage=None,
        scored_criterion_coverage=None,
        publication_status=CallScorePublicationStatus.NO_SCORABLE_CRITERIA,
        quality_flags=(AggregationQualityFlag.NO_SCORABLE_CRITERIA,),
    )
    with pytest.raises(FrozenInstanceError):
        result.call_id = "changed"  # type: ignore[misc]
