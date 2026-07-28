"""Evaluation exception hierarchy with log-safe messages."""

from sales_call_agent.domain.exceptions import DomainError


class EvaluationError(DomainError):
    """Base class for evaluation boundary failures."""


class InvalidEvaluationInputError(EvaluationError):
    """Raised when evaluation request/source relationships are invalid."""


class EvaluationProviderUnavailableError(EvaluationError):
    """Raised when an evaluation provider cannot be used."""


class EvaluationRequestFailedError(EvaluationError):
    """Raised when provider evaluation execution fails."""


class EvaluationTimeoutError(EvaluationError):
    """Raised when an evaluation request times out."""


class InvalidEvaluationResponseError(EvaluationError):
    """Raised when provider output violates evaluation contracts."""


class UnsupportedEvaluationConfigurationError(EvaluationError):
    """Raised when a provider or fake evaluator configuration is unsupported."""
