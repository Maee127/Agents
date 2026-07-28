"""Aggregation exception hierarchy with log-safe messages."""

from sales_call_agent.domain.exceptions import DomainError


class AggregationError(DomainError):
    """Base class for call-level scoring aggregation failures."""


class InvalidAggregationInputError(AggregationError):
    """Raised when aggregation request continuity or coverage is invalid."""


class InvalidCriterionContributionError(AggregationError):
    """Raised when a criterion contribution violates local invariants."""


class UnsupportedScoringScaleError(AggregationError):
    """Raised when a criterion scale is incompatible with aggregation rules."""


class AggregationCalculationError(AggregationError):
    """Raised when numeric aggregation outputs are non-finite or inconsistent."""


class InvalidCallScoreResultError(AggregationError):
    """Raised when final call-score result fields and flags are inconsistent."""
