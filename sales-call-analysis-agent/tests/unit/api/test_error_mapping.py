"""Unit tests for exception-to-HTTP error mapping."""

from __future__ import annotations

from sales_call_agent.api.errors import map_pipeline_error
from sales_call_agent.api.schemas.errors import ApiErrorCode
from sales_call_agent.orchestration.exceptions import (
    InvalidPipelineRequestError,
    PipelineConflictError,
    PipelinePrerequisiteError,
    PipelineStageExecutionError,
    PipelineStagePersistenceError,
)
from sales_call_agent.orchestration.models import (
    PipelineFailureReason,
    PipelineRetryClassification,
    PipelineStage,
)


def _exec_error(
    reason: PipelineFailureReason,
    retry: PipelineRetryClassification,
    stage: PipelineStage | None = PipelineStage.TRANSCRIPTION,
) -> PipelineStageExecutionError:
    return PipelineStageExecutionError(
        "test",
        stage=stage,
        reason_code=reason,
        retry_classification=retry,
    )


def test_invalid_request_maps_to_400() -> None:
    exc = InvalidPipelineRequestError(
        "bad req",
        stage=None,
        reason_code=PipelineFailureReason.INVALID_REQUEST,
        retry_classification=PipelineRetryClassification.NON_RETRYABLE,
    )
    status, body = map_pipeline_error(exc)
    assert status == 400
    assert body.error_code is ApiErrorCode.INVALID_REQUEST
    assert body.retryable is False


def test_rubric_not_approved_maps_to_409_via_prerequisite() -> None:
    exc = PipelinePrerequisiteError(
        "not approved",
        stage=None,
        reason_code=PipelineFailureReason.RUBRIC_NOT_APPROVED,
        retry_classification=PipelineRetryClassification.NON_RETRYABLE,
    )
    status, body = map_pipeline_error(exc)
    assert status == 409
    assert body.error_code is ApiErrorCode.RUBRIC_NOT_APPROVED


def test_prerequisite_maps_to_409() -> None:
    exc = PipelinePrerequisiteError(
        "missing",
        stage=None,
        reason_code=PipelineFailureReason.MISSING_PREREQUISITE,
        retry_classification=PipelineRetryClassification.NON_RETRYABLE,
    )
    status, body = map_pipeline_error(exc)
    assert status == 409
    assert body.error_code is ApiErrorCode.PREREQUISITE_NOT_MET


def test_conflict_maps_to_409() -> None:
    exc = PipelineConflictError(
        "conflict",
        stage=None,
        reason_code=PipelineFailureReason.PERSISTENCE_CONFLICT,
        retry_classification=PipelineRetryClassification.CONFLICT_RELOAD_REQUIRED,
    )
    status, body = map_pipeline_error(exc)
    assert status == 409
    assert body.error_code is ApiErrorCode.PIPELINE_CONFLICT


def test_retryable_provider_unavailable_maps_to_503() -> None:
    exc = _exec_error(
        PipelineFailureReason.PROVIDER_UNAVAILABLE,
        PipelineRetryClassification.RETRYABLE,
    )
    status, body = map_pipeline_error(exc)
    assert status == 503
    assert body.retryable is True
    assert body.error_code is ApiErrorCode.PROVIDER_UNAVAILABLE


def test_non_retryable_invalid_provider_output_maps_to_502() -> None:
    exc = _exec_error(
        PipelineFailureReason.INVALID_PROVIDER_OUTPUT,
        PipelineRetryClassification.NON_RETRYABLE,
    )
    status, body = map_pipeline_error(exc)
    assert status == 502
    assert body.retryable is False
    assert body.error_code is ApiErrorCode.PROVIDER_RESPONSE_INVALID


def test_stage_preserved_in_error_response() -> None:
    exc = _exec_error(
        PipelineFailureReason.PROVIDER_UNAVAILABLE,
        PipelineRetryClassification.RETRYABLE,
        stage=PipelineStage.DIARIZATION,
    )
    _status, body = map_pipeline_error(exc)
    assert body.stage == "diarization"


def test_persistence_error_repository_unavailable_maps_to_503() -> None:
    exc = PipelineStagePersistenceError(
        "repo down",
        stage=PipelineStage.TRANSCRIPTION,
        reason_code=PipelineFailureReason.REPOSITORY_UNAVAILABLE,
        retry_classification=PipelineRetryClassification.RETRYABLE,
    )
    status, body = map_pipeline_error(exc)
    assert status == 503
    assert body.error_code is ApiErrorCode.REPOSITORY_UNAVAILABLE
    assert body.retryable is True
