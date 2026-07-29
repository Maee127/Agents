"""Orchestration exception taxonomy with privacy-safe messages."""

from __future__ import annotations

from sales_call_agent.orchestration.models import (
    PipelineFailureReason,
    PipelineRetryClassification,
    PipelineStage,
)


class PipelineOrchestrationError(Exception):
    """Base class for application-layer pipeline orchestration failures."""

    def __init__(
        self,
        message: str,
        *,
        stage: PipelineStage | None = None,
        reason_code: PipelineFailureReason,
        retry_classification: PipelineRetryClassification,
    ) -> None:
        super().__init__(message)
        self._stage = stage
        self._reason_code = reason_code
        self._retry_classification = retry_classification

    @property
    def stage(self) -> PipelineStage | None:
        return self._stage

    @property
    def reason_code(self) -> PipelineFailureReason:
        return self._reason_code

    @property
    def retry_classification(self) -> PipelineRetryClassification:
        return self._retry_classification

    def __str__(self) -> str:
        return self.args[0] if self.args else self.__class__.__name__

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"stage={self._stage!r}, "
            f"reason_code={self._reason_code!r}, "
            f"retry_classification={self._retry_classification!r})"
        )


class InvalidPipelineRequestError(PipelineOrchestrationError):
    """Raised when orchestration request fields or target rules are invalid."""


class PipelinePrerequisiteError(PipelineOrchestrationError):
    """Raised when required persisted prerequisites are missing or inconsistent."""


class PipelineStageExecutionError(PipelineOrchestrationError):
    """Raised when a stage provider or deterministic engine fails."""


class PipelineStagePersistenceError(PipelineOrchestrationError):
    """Raised when stage persistence or status updates fail unexpectedly."""


class PipelineConflictError(PipelineOrchestrationError):
    """Raised when concurrent canonical-result conflicts cannot be reconciled."""
