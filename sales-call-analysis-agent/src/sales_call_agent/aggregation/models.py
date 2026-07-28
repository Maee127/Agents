"""Immutable contracts for deterministic call-level scoring aggregation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sales_call_agent.aggregation.exceptions import (
    InvalidAggregationInputError,
    InvalidCallScoreResultError,
    InvalidCriterionContributionError,
)
from sales_call_agent.evaluation.models import (
    CallEvaluationResult,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    HumanReviewReason,
)
from sales_call_agent.knowledge.models import RubricStatus, SalesRubric

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_WARNING_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class CallScorePublicationStatus(StrEnum):
    """Publication-readiness classification for call-level score output."""

    PUBLISHABLE = "publishable"
    LIMITED_COVERAGE = "limited_coverage"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    NO_SCORABLE_CRITERIA = "no_scorable_criteria"


class AggregationQualityFlag(StrEnum):
    """Quality and completeness conditions for call-level score results."""

    INSUFFICIENT_EVIDENCE_PRESENT = "insufficient_evidence_present"
    NOT_APPLICABLE_CRITERIA_PRESENT = "not_applicable_criteria_present"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    LIMITED_WEIGHT_COVERAGE = "limited_weight_coverage"
    LIMITED_CRITERION_COVERAGE = "limited_criterion_coverage"
    NO_SCORABLE_CRITERIA = "no_scorable_criteria"
    PARTIAL_SCORE = "partial_score"
    FULLY_SCORED_APPLICABLE_RUBRIC = "fully_scored_applicable_rubric"
    ZERO_PERFORMANCE_SCORE = "zero_performance_score"


def _ensure_required_string(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise error(f"{field_name} must be non-empty and trimmed")


def _ensure_safe_identifier(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe identifier")
    if "/" in value or "\\" in value or ":" in value:
        raise error(f"{field_name} must not contain path-like characters")


def _ensure_safe_warning_code(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SAFE_WARNING_CODE_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe warning code")


def _ensure_enum_member(
    value: object,
    enum_type: type[Enum],
    field_name: str,
    error: type[Exception],
) -> None:
    if not isinstance(value, enum_type):
        raise error(f"{field_name} must be a {enum_type.__name__} member")


def _ensure_finite_number(value: object, field_name: str, error: type[Exception]) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error(f"{field_name} must be a number")
    if not math.isfinite(float(value)):
        raise error(f"{field_name} must be finite")


def _ensure_finite_ratio(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_finite_number(value, field_name, error)
    assert isinstance(value, int | float)
    if float(value) < 0.0 or float(value) > 1.0:
        raise error(f"{field_name} must be between 0.0 and 1.0")


def _is_scored_reason(reason: CriterionEvaluationReason) -> bool:
    return reason in {
        CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
        CriterionEvaluationReason.SUPPORTED_BY_ABSENCE_EVIDENCE,
    }


def _is_not_applicable_reason(reason: CriterionEvaluationReason) -> bool:
    return reason in {
        CriterionEvaluationReason.REQUIRED_ROLE_NOT_PRESENT,
        CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
    }


def _is_insufficient_reason(reason: CriterionEvaluationReason) -> bool:
    return reason in {
        CriterionEvaluationReason.NO_VALID_EVIDENCE,
        CriterionEvaluationReason.INSUFFICIENT_EVIDENCE_SPANS,
        CriterionEvaluationReason.SELLER_ROLE_UNRESOLVED,
        CriterionEvaluationReason.CUSTOMER_CONTEXT_MISSING,
        CriterionEvaluationReason.TIMESTAMP_EVIDENCE_MISSING,
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class AggregationConfig:
    """Deterministic policy thresholds for call-level score publication."""

    minimum_scored_weight_coverage: float = 0.70
    minimum_scored_criterion_coverage: float = 0.70
    require_no_human_review_for_publish: bool = True

    def __post_init__(self) -> None:
        _ensure_finite_ratio(
            self.minimum_scored_weight_coverage,
            "minimum_scored_weight_coverage",
            InvalidAggregationInputError,
        )
        _ensure_finite_ratio(
            self.minimum_scored_criterion_coverage,
            "minimum_scored_criterion_coverage",
            InvalidAggregationInputError,
        )
        if not isinstance(self.require_no_human_review_for_publish, bool):
            raise InvalidAggregationInputError(
                "require_no_human_review_for_publish must be a boolean"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CriterionScoreContribution:
    """One rubric criterion's contribution state in call-level aggregation."""

    criterion_id: str
    status: CriterionEvaluationStatus
    criterion_weight: float
    raw_score: float | None
    normalized_score: float | None
    weighted_points: float | None
    human_review_required: bool
    human_review_reason: HumanReviewReason | None
    reason_code: CriterionEvaluationReason
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_identifier(
            self.criterion_id,
            "criterion_id",
            InvalidCriterionContributionError,
        )
        _ensure_enum_member(
            self.status,
            CriterionEvaluationStatus,
            "status",
            InvalidCriterionContributionError,
        )
        _ensure_finite_number(
            self.criterion_weight,
            "criterion_weight",
            InvalidCriterionContributionError,
        )
        assert isinstance(self.criterion_weight, int | float)
        if float(self.criterion_weight) <= 0.0:
            raise InvalidCriterionContributionError("criterion_weight must be greater than zero")

        if self.raw_score is not None:
            _ensure_finite_number(self.raw_score, "raw_score", InvalidCriterionContributionError)
        if self.normalized_score is not None:
            _ensure_finite_ratio(
                self.normalized_score,
                "normalized_score",
                InvalidCriterionContributionError,
            )
        if self.weighted_points is not None:
            _ensure_finite_number(
                self.weighted_points,
                "weighted_points",
                InvalidCriterionContributionError,
            )

        if not isinstance(self.human_review_required, bool):
            raise InvalidCriterionContributionError("human_review_required must be a boolean")
        if self.human_review_required:
            if self.human_review_reason is None:
                raise InvalidCriterionContributionError(
                    "human_review_reason is required when human_review_required is true"
                )
            _ensure_enum_member(
                self.human_review_reason,
                HumanReviewReason,
                "human_review_reason",
                InvalidCriterionContributionError,
            )
        elif self.human_review_reason is not None:
            raise InvalidCriterionContributionError(
                "human_review_reason must be absent when human_review_required is false"
            )

        _ensure_enum_member(
            self.reason_code,
            CriterionEvaluationReason,
            "reason_code",
            InvalidCriterionContributionError,
        )

        if self.status is CriterionEvaluationStatus.SCORED:
            if (
                self.raw_score is None
                or self.normalized_score is None
                or self.weighted_points is None
            ):
                raise InvalidCriterionContributionError(
                    "scored contributions require raw_score, normalized_score, and weighted_points"
                )
            assert isinstance(self.normalized_score, int | float)
            assert isinstance(self.weighted_points, int | float)
            expected_points = float(self.normalized_score) * float(self.criterion_weight)
            if not math.isclose(
                float(self.weighted_points),
                expected_points,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise InvalidCriterionContributionError(
                    "weighted_points must equal normalized_score * criterion_weight"
                )
            if not _is_scored_reason(self.reason_code):
                raise InvalidCriterionContributionError(
                    "scored contributions require a scored reason code"
                )
        elif self.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE:
            if (
                self.raw_score is not None
                or self.normalized_score is not None
                or self.weighted_points is not None
            ):
                raise InvalidCriterionContributionError(
                    "insufficient-evidence contributions must not include score values"
                )
            if not _is_insufficient_reason(self.reason_code):
                raise InvalidCriterionContributionError(
                    "insufficient-evidence contributions require an insufficient reason code"
                )
        elif self.status is CriterionEvaluationStatus.NOT_APPLICABLE:
            if (
                self.raw_score is not None
                or self.normalized_score is not None
                or self.weighted_points is not None
            ):
                raise InvalidCriterionContributionError(
                    "not-applicable contributions must not include score values"
                )
            if not _is_not_applicable_reason(self.reason_code):
                raise InvalidCriterionContributionError(
                    "not-applicable contributions require a not-applicable reason code"
                )

        for code in self.warning_codes:
            _ensure_safe_warning_code(
                code,
                "warning_codes",
                InvalidCriterionContributionError,
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class AggregationRequest:
    """Input contract for deterministic call-level score aggregation."""

    call_id: str
    rubric: SalesRubric = field(repr=False)
    evaluation: CallEvaluationResult = field(repr=False)
    config: AggregationConfig = field(default_factory=AggregationConfig)

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.call_id, "call_id", InvalidAggregationInputError)
        if not isinstance(self.rubric, SalesRubric):
            raise InvalidAggregationInputError("rubric must be a SalesRubric")
        if not isinstance(self.evaluation, CallEvaluationResult):
            raise InvalidAggregationInputError("evaluation must be a CallEvaluationResult")
        if not isinstance(self.config, AggregationConfig):
            raise InvalidAggregationInputError("config must be an AggregationConfig")

        if self.rubric.status is not RubricStatus.APPROVED:
            raise InvalidAggregationInputError("rubric status must be APPROVED")
        if not self.rubric.criteria:
            raise InvalidAggregationInputError(
                "approved rubric must contain at least one criterion"
            )
        if self.call_id != self.evaluation.call_id:
            raise InvalidAggregationInputError("evaluation call_id must match request call_id")
        if self.rubric.rubric_id != self.evaluation.rubric_id:
            raise InvalidAggregationInputError("evaluation rubric_id must match request rubric_id")
        if self.rubric.version != self.evaluation.rubric_version:
            raise InvalidAggregationInputError(
                "evaluation rubric_version must match request rubric version"
            )

        rubric_ids = tuple(item.criterion_id for item in self.rubric.criteria)
        eval_ids = tuple(item.criterion_id for item in self.evaluation.criterion_evaluations)
        if rubric_ids != eval_ids:
            raise InvalidAggregationInputError(
                "evaluation criterion IDs must exactly match rubric criteria in order"
            )
        if len(set(eval_ids)) != len(eval_ids):
            raise InvalidAggregationInputError("evaluation criterion IDs must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class CallScoreResult:
    """Deterministic call-level score and coverage result."""

    call_id: str
    rubric_id: str
    rubric_version: str
    config: AggregationConfig
    criterion_contributions: tuple[CriterionScoreContribution, ...]
    weighted_performance_score: float | None
    scored_weight_coverage: float | None
    scored_criterion_coverage: float | None
    publication_status: CallScorePublicationStatus
    quality_flags: tuple[AggregationQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.call_id, "call_id", InvalidCallScoreResultError)
        _ensure_safe_identifier(self.rubric_id, "rubric_id", InvalidCallScoreResultError)
        _ensure_required_string(
            self.rubric_version,
            "rubric_version",
            InvalidCallScoreResultError,
        )
        if not isinstance(self.config, AggregationConfig):
            raise InvalidCallScoreResultError("config must be an AggregationConfig")

        seen_ids: set[str] = set()
        for contribution in self.criterion_contributions:
            if not isinstance(contribution, CriterionScoreContribution):
                raise InvalidCallScoreResultError(
                    "criterion_contributions must contain CriterionScoreContribution values"
                )
            if contribution.criterion_id in seen_ids:
                raise InvalidCallScoreResultError("criterion contribution IDs must be unique")
            seen_ids.add(contribution.criterion_id)

        if self.weighted_performance_score is not None:
            _ensure_finite_ratio(
                self.weighted_performance_score,
                "weighted_performance_score",
                InvalidCallScoreResultError,
            )
        if self.scored_weight_coverage is not None:
            _ensure_finite_ratio(
                self.scored_weight_coverage,
                "scored_weight_coverage",
                InvalidCallScoreResultError,
            )
        if self.scored_criterion_coverage is not None:
            _ensure_finite_ratio(
                self.scored_criterion_coverage,
                "scored_criterion_coverage",
                InvalidCallScoreResultError,
            )

        _ensure_enum_member(
            self.publication_status,
            CallScorePublicationStatus,
            "publication_status",
            InvalidCallScoreResultError,
        )

        for flag in self.quality_flags:
            _ensure_enum_member(
                flag,
                AggregationQualityFlag,
                "quality_flags",
                InvalidCallScoreResultError,
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidCallScoreResultError)

        _validate_quality_flag_consistency(self)
        _validate_publication_status_consistency(self)

    @property
    def total_criterion_count(self) -> int:
        return len(self.criterion_contributions)

    @property
    def scored_count(self) -> int:
        return sum(
            1
            for item in self.criterion_contributions
            if item.status is CriterionEvaluationStatus.SCORED
        )

    @property
    def insufficient_evidence_count(self) -> int:
        return sum(
            1
            for item in self.criterion_contributions
            if item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
        )

    @property
    def not_applicable_count(self) -> int:
        return sum(
            1
            for item in self.criterion_contributions
            if item.status is CriterionEvaluationStatus.NOT_APPLICABLE
        )

    @property
    def human_review_count(self) -> int:
        return sum(1 for item in self.criterion_contributions if item.human_review_required)

    @property
    def total_rubric_weight(self) -> float:
        return math.fsum(item.criterion_weight for item in self.criterion_contributions)

    @property
    def scored_weight(self) -> float:
        return math.fsum(
            item.criterion_weight
            for item in self.criterion_contributions
            if item.status is CriterionEvaluationStatus.SCORED
        )

    @property
    def insufficient_evidence_weight(self) -> float:
        return math.fsum(
            item.criterion_weight
            for item in self.criterion_contributions
            if item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
        )

    @property
    def not_applicable_weight(self) -> float:
        return math.fsum(
            item.criterion_weight
            for item in self.criterion_contributions
            if item.status is CriterionEvaluationStatus.NOT_APPLICABLE
        )

    @property
    def applicable_weight(self) -> float:
        return math.fsum(
            item.criterion_weight
            for item in self.criterion_contributions
            if item.status
            in {
                CriterionEvaluationStatus.SCORED,
                CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
            }
        )

    @property
    def has_numeric_score(self) -> bool:
        return self.weighted_performance_score is not None


def _validate_quality_flag_consistency(result: CallScoreResult) -> None:
    flags = set(result.quality_flags)
    scored_count = result.scored_count
    insufficient_count = result.insufficient_evidence_count
    not_applicable_count = result.not_applicable_count
    applicable_count = scored_count + insufficient_count
    has_human_review = result.human_review_count > 0

    has_insufficient = insufficient_count > 0
    has_not_applicable = not_applicable_count > 0
    no_scorable = scored_count == 0
    partial_score = scored_count > 0 and insufficient_count > 0
    fully_scored = (
        applicable_count > 0 and insufficient_count == 0 and scored_count == applicable_count
    )
    limited_weight = (
        result.scored_weight_coverage is not None
        and result.scored_weight_coverage < result.config.minimum_scored_weight_coverage
    )
    limited_criterion = (
        result.scored_criterion_coverage is not None
        and result.scored_criterion_coverage < result.config.minimum_scored_criterion_coverage
    )
    zero_score = (
        result.weighted_performance_score is not None and result.weighted_performance_score == 0.0
    )

    _require_flag_match(
        condition=has_insufficient,
        flag=AggregationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT,
        flags=flags,
        message="INSUFFICIENT_EVIDENCE_PRESENT must match contributions",
    )
    _require_flag_match(
        condition=has_not_applicable,
        flag=AggregationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT,
        flags=flags,
        message="NOT_APPLICABLE_CRITERIA_PRESENT must match contributions",
    )
    _require_flag_match(
        condition=has_human_review,
        flag=AggregationQualityFlag.HUMAN_REVIEW_REQUIRED,
        flags=flags,
        message="HUMAN_REVIEW_REQUIRED must match contributions",
    )
    _require_flag_match(
        condition=limited_weight,
        flag=AggregationQualityFlag.LIMITED_WEIGHT_COVERAGE,
        flags=flags,
        message="LIMITED_WEIGHT_COVERAGE must match coverage thresholds",
    )
    _require_flag_match(
        condition=limited_criterion,
        flag=AggregationQualityFlag.LIMITED_CRITERION_COVERAGE,
        flags=flags,
        message="LIMITED_CRITERION_COVERAGE must match coverage thresholds",
    )
    _require_flag_match(
        condition=no_scorable,
        flag=AggregationQualityFlag.NO_SCORABLE_CRITERIA,
        flags=flags,
        message="NO_SCORABLE_CRITERIA must match scored criterion count",
    )
    _require_flag_match(
        condition=partial_score,
        flag=AggregationQualityFlag.PARTIAL_SCORE,
        flags=flags,
        message="PARTIAL_SCORE must match scored and insufficient contributions",
    )
    _require_flag_match(
        condition=fully_scored,
        flag=AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC,
        flags=flags,
        message="FULLY_SCORED_APPLICABLE_RUBRIC must match applicable scoring state",
    )
    _require_flag_match(
        condition=zero_score,
        flag=AggregationQualityFlag.ZERO_PERFORMANCE_SCORE,
        flags=flags,
        message="ZERO_PERFORMANCE_SCORE must match weighted performance score",
    )

    if (
        AggregationQualityFlag.NO_SCORABLE_CRITERIA in flags
        and AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC in flags
    ):
        raise InvalidCallScoreResultError(
            "NO_SCORABLE_CRITERIA and FULLY_SCORED_APPLICABLE_RUBRIC must be mutually exclusive"
        )
    if (
        AggregationQualityFlag.PARTIAL_SCORE in flags
        and AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC in flags
    ):
        raise InvalidCallScoreResultError(
            "PARTIAL_SCORE and FULLY_SCORED_APPLICABLE_RUBRIC must be mutually exclusive"
        )


def _validate_publication_status_consistency(result: CallScoreResult) -> None:
    limited = (
        AggregationQualityFlag.LIMITED_WEIGHT_COVERAGE in result.quality_flags
        or AggregationQualityFlag.LIMITED_CRITERION_COVERAGE in result.quality_flags
    )
    has_human_review = result.human_review_count > 0

    expected = CallScorePublicationStatus.PUBLISHABLE
    if result.scored_count == 0 or result.weighted_performance_score is None:
        expected = CallScorePublicationStatus.NO_SCORABLE_CRITERIA
    elif has_human_review and result.config.require_no_human_review_for_publish:
        expected = CallScorePublicationStatus.HUMAN_REVIEW_REQUIRED
    elif limited:
        expected = CallScorePublicationStatus.LIMITED_COVERAGE

    if result.publication_status is not expected:
        raise InvalidCallScoreResultError(
            "publication_status must follow contribution state and stored config"
        )


def _require_flag_match(
    *,
    condition: bool,
    flag: AggregationQualityFlag,
    flags: set[AggregationQualityFlag],
    message: str,
) -> None:
    if (flag in flags) != condition:
        raise InvalidCallScoreResultError(message)
