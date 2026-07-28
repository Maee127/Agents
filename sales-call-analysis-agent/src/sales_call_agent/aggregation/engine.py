"""Deterministic call-level scoring and coverage aggregation engine."""

from __future__ import annotations

import math

from sales_call_agent.aggregation.exceptions import (
    AggregationCalculationError,
    InvalidAggregationInputError,
    UnsupportedScoringScaleError,
)
from sales_call_agent.aggregation.models import (
    AggregationConfig,
    AggregationQualityFlag,
    AggregationRequest,
    CallScorePublicationStatus,
    CallScoreResult,
    CriterionScoreContribution,
)
from sales_call_agent.evaluation.models import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
)
from sales_call_agent.knowledge.models import RubricCriterion


def aggregate_call_evaluation(request: AggregationRequest) -> CallScoreResult:
    """Aggregate criterion-level evaluations into deterministic call-level scoring."""
    if not isinstance(request, AggregationRequest):
        raise InvalidAggregationInputError("request must be an AggregationRequest")

    rubric_criteria = request.rubric.criteria
    evals = request.evaluation.criterion_evaluations
    if len(rubric_criteria) != len(evals):
        raise InvalidAggregationInputError(
            "evaluation criterion coverage must exactly match rubric criteria"
        )

    contributions: list[CriterionScoreContribution] = []
    for rubric_criterion, criterion_eval in zip(rubric_criteria, evals, strict=True):
        contribution = _build_contribution(rubric_criterion, criterion_eval)
        contributions.append(contribution)

    scored_weights = [
        item.criterion_weight
        for item in contributions
        if item.status is CriterionEvaluationStatus.SCORED
    ]
    scored_points = [
        float(item.weighted_points)
        for item in contributions
        if item.status is CriterionEvaluationStatus.SCORED and item.weighted_points is not None
    ]
    applicable_weights = [
        item.criterion_weight
        for item in contributions
        if item.status
        in {
            CriterionEvaluationStatus.SCORED,
            CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
        }
    ]

    scored_weight = math.fsum(scored_weights)
    total_weighted_points = math.fsum(scored_points)
    applicable_weight = math.fsum(applicable_weights)

    weighted_performance_score: float | None = None
    if scored_weight > 0:
        weighted_performance_score = total_weighted_points / scored_weight
        if not math.isfinite(weighted_performance_score):
            raise AggregationCalculationError("weighted performance score must be finite")
        if weighted_performance_score < 0.0 or weighted_performance_score > 1.0:
            raise AggregationCalculationError("weighted performance score must be in [0.0, 1.0]")

    scored_weight_coverage: float | None = None
    if applicable_weight > 0:
        scored_weight_coverage = scored_weight / applicable_weight
        if not math.isfinite(scored_weight_coverage):
            raise AggregationCalculationError("scored weight coverage must be finite")
        if scored_weight_coverage < 0.0 or scored_weight_coverage > 1.0:
            raise AggregationCalculationError("scored weight coverage must be in [0.0, 1.0]")

    scored_count = sum(
        1 for item in contributions if item.status is CriterionEvaluationStatus.SCORED
    )
    insufficient_count = sum(
        1
        for item in contributions
        if item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
    )
    applicable_count = scored_count + insufficient_count

    scored_criterion_coverage: float | None = None
    if applicable_count > 0:
        scored_criterion_coverage = scored_count / applicable_count
        if not math.isfinite(scored_criterion_coverage):
            raise AggregationCalculationError("scored criterion coverage must be finite")
        if scored_criterion_coverage < 0.0 or scored_criterion_coverage > 1.0:
            raise AggregationCalculationError("scored criterion coverage must be in [0.0, 1.0]")

    flags = _derive_quality_flags(
        contributions=tuple(contributions),
        config=request.config,
        weighted_performance_score=weighted_performance_score,
        scored_weight_coverage=scored_weight_coverage,
        scored_criterion_coverage=scored_criterion_coverage,
    )
    status = _derive_publication_status(
        contributions=tuple(contributions),
        config=request.config,
        weighted_performance_score=weighted_performance_score,
        flags=flags,
    )

    return CallScoreResult(
        call_id=request.call_id,
        rubric_id=request.rubric.rubric_id,
        rubric_version=request.rubric.version,
        config=request.config,
        criterion_contributions=tuple(contributions),
        weighted_performance_score=weighted_performance_score,
        scored_weight_coverage=scored_weight_coverage,
        scored_criterion_coverage=scored_criterion_coverage,
        publication_status=status,
        quality_flags=flags,
    )


def _build_contribution(
    criterion: RubricCriterion,
    criterion_eval: CriterionEvaluation,
) -> CriterionScoreContribution:
    levels = criterion.scoring_scale.levels
    if len(levels) < 2:
        raise UnsupportedScoringScaleError("criterion scales must have at least two score levels")

    scale_min = float(levels[0].score)
    scale_max = float(levels[-1].score)
    if not math.isfinite(scale_min) or not math.isfinite(scale_max) or scale_max <= scale_min:
        raise UnsupportedScoringScaleError("criterion scale bounds must be finite and increasing")

    raw_score = criterion_eval.score
    normalized_score: float | None = None
    weighted_points: float | None = None
    if criterion_eval.status is CriterionEvaluationStatus.SCORED:
        if raw_score is None:
            raise AggregationCalculationError("scored criterion must provide a raw score")
        if float(raw_score) not in {float(level.score) for level in levels}:
            raise AggregationCalculationError("raw score must match one allowed scale value")
        normalized_score = (float(raw_score) - scale_min) / (scale_max - scale_min)
        if not math.isfinite(normalized_score):
            raise AggregationCalculationError("normalized score must be finite")
        if normalized_score < 0.0 or normalized_score > 1.0:
            raise AggregationCalculationError("normalized score must be in [0.0, 1.0]")
        weighted_points = normalized_score * float(criterion.weight)
        if not math.isfinite(weighted_points):
            raise AggregationCalculationError("weighted points must be finite")

    return CriterionScoreContribution(
        criterion_id=criterion_eval.criterion_id,
        status=criterion_eval.status,
        criterion_weight=float(criterion.weight),
        raw_score=raw_score,
        normalized_score=normalized_score,
        weighted_points=weighted_points,
        human_review_required=criterion_eval.human_review_required,
        human_review_reason=criterion_eval.human_review_reason,
        reason_code=criterion_eval.reason_code,
        warning_codes=criterion_eval.warning_codes,
    )


def _derive_quality_flags(
    *,
    contributions: tuple[CriterionScoreContribution, ...],
    config: AggregationConfig,
    weighted_performance_score: float | None,
    scored_weight_coverage: float | None,
    scored_criterion_coverage: float | None,
) -> tuple[AggregationQualityFlag, ...]:
    scored_count = sum(
        1 for item in contributions if item.status is CriterionEvaluationStatus.SCORED
    )
    insufficient_count = sum(
        1
        for item in contributions
        if item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
    )
    not_applicable_count = sum(
        1 for item in contributions if item.status is CriterionEvaluationStatus.NOT_APPLICABLE
    )
    applicable_count = scored_count + insufficient_count

    flags: set[AggregationQualityFlag] = set()
    if insufficient_count > 0:
        flags.add(AggregationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT)
    if not_applicable_count > 0:
        flags.add(AggregationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT)
    if any(item.human_review_required for item in contributions):
        flags.add(AggregationQualityFlag.HUMAN_REVIEW_REQUIRED)
    if (
        scored_weight_coverage is not None
        and scored_weight_coverage < config.minimum_scored_weight_coverage
    ):
        flags.add(AggregationQualityFlag.LIMITED_WEIGHT_COVERAGE)
    if (
        scored_criterion_coverage is not None
        and scored_criterion_coverage < config.minimum_scored_criterion_coverage
    ):
        flags.add(AggregationQualityFlag.LIMITED_CRITERION_COVERAGE)
    if scored_count == 0:
        flags.add(AggregationQualityFlag.NO_SCORABLE_CRITERIA)
    if scored_count > 0 and insufficient_count > 0:
        flags.add(AggregationQualityFlag.PARTIAL_SCORE)
    if applicable_count > 0 and insufficient_count == 0 and scored_count == applicable_count:
        flags.add(AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC)
    if weighted_performance_score is not None and weighted_performance_score == 0.0:
        flags.add(AggregationQualityFlag.ZERO_PERFORMANCE_SCORE)

    return tuple(sorted(flags, key=lambda item: item.value))


def _derive_publication_status(
    *,
    contributions: tuple[CriterionScoreContribution, ...],
    config: AggregationConfig,
    weighted_performance_score: float | None,
    flags: tuple[AggregationQualityFlag, ...],
) -> CallScorePublicationStatus:
    scored_count = sum(
        1 for item in contributions if item.status is CriterionEvaluationStatus.SCORED
    )
    if scored_count == 0 or weighted_performance_score is None:
        return CallScorePublicationStatus.NO_SCORABLE_CRITERIA

    has_human_review = any(item.human_review_required for item in contributions)
    if has_human_review and config.require_no_human_review_for_publish:
        return CallScorePublicationStatus.HUMAN_REVIEW_REQUIRED

    if (
        AggregationQualityFlag.LIMITED_WEIGHT_COVERAGE in flags
        or AggregationQualityFlag.LIMITED_CRITERION_COVERAGE in flags
    ):
        return CallScorePublicationStatus.LIMITED_COVERAGE

    return CallScorePublicationStatus.PUBLISHABLE
