"""Exception-to-HTTP mapping and exception handlers for the v1 API."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sales_call_agent.api.schemas.errors import ApiErrorCode, ApiErrorFieldError, ApiErrorResponse
from sales_call_agent.orchestration.exceptions import (
    InvalidPipelineRequestError,
    PipelineConflictError,
    PipelineOrchestrationError,
    PipelinePrerequisiteError,
    PipelineStageExecutionError,
    PipelineStagePersistenceError,
)
from sales_call_agent.orchestration.models import (
    PipelineFailureReason,
    PipelineRetryClassification,
)
from sales_call_agent.persistence.exceptions import (
    RecordAlreadyExistsError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleRecordVersionError,
)

_EXECUTION_REASON_TO_CODE: dict[PipelineFailureReason, ApiErrorCode] = {
    PipelineFailureReason.PROVIDER_UNAVAILABLE: ApiErrorCode.PROVIDER_UNAVAILABLE,
    PipelineFailureReason.PROVIDER_TIMEOUT: ApiErrorCode.PROVIDER_TIMEOUT,
    PipelineFailureReason.INVALID_PROVIDER_OUTPUT: ApiErrorCode.PROVIDER_RESPONSE_INVALID,
    PipelineFailureReason.PROVIDER_REQUEST_FAILED: ApiErrorCode.PROVIDER_RESPONSE_INVALID,
    PipelineFailureReason.UNSUPPORTED_CONFIGURATION: ApiErrorCode.PROVIDER_RESPONSE_INVALID,
    PipelineFailureReason.STAGE_EXECUTION_FAILED: ApiErrorCode.PROVIDER_RESPONSE_INVALID,
    PipelineFailureReason.RUBRIC_NOT_APPROVED: ApiErrorCode.RUBRIC_NOT_APPROVED,
    PipelineFailureReason.STALE_REVISION: ApiErrorCode.RESOURCE_CONFLICT,
    PipelineFailureReason.PERSISTENCE_CONFLICT: ApiErrorCode.RESOURCE_CONFLICT,
    PipelineFailureReason.REPOSITORY_UNAVAILABLE: ApiErrorCode.REPOSITORY_UNAVAILABLE,
    PipelineFailureReason.MALFORMED_PERSISTED_DATA: ApiErrorCode.PROVIDER_RESPONSE_INVALID,
}

_EXECUTION_STATUS_TO_HTTP: dict[tuple[PipelineRetryClassification, ApiErrorCode], int] = {}


def _http_status_for_orchestration(exc: PipelineOrchestrationError) -> int:
    classification = exc.retry_classification
    if classification is PipelineRetryClassification.RETRYABLE:
        code = _EXECUTION_REASON_TO_CODE.get(exc.reason_code, ApiErrorCode.PROVIDER_UNAVAILABLE)
        if code is ApiErrorCode.PROVIDER_TIMEOUT:
            return 504
        if code is ApiErrorCode.REPOSITORY_UNAVAILABLE:
            return 503
        return 503
    if classification is PipelineRetryClassification.CONFLICT_RELOAD_REQUIRED:
        return 409
    # NON_RETRYABLE
    code = _EXECUTION_REASON_TO_CODE.get(exc.reason_code, ApiErrorCode.INTERNAL_ERROR)
    if code is ApiErrorCode.RUBRIC_NOT_APPROVED:
        return 409
    if code is ApiErrorCode.RESOURCE_CONFLICT:
        return 409
    return 502


def _error_code_for_orchestration(exc: PipelineOrchestrationError) -> ApiErrorCode:
    if isinstance(exc, InvalidPipelineRequestError):
        reason = exc.reason_code
        if reason is PipelineFailureReason.RUBRIC_NOT_APPROVED:
            return ApiErrorCode.RUBRIC_NOT_APPROVED
        return ApiErrorCode.INVALID_REQUEST
    if isinstance(exc, PipelinePrerequisiteError):
        reason = exc.reason_code
        if reason is PipelineFailureReason.RUBRIC_NOT_APPROVED:
            return ApiErrorCode.RUBRIC_NOT_APPROVED
        return ApiErrorCode.PREREQUISITE_NOT_MET
    if isinstance(exc, PipelineConflictError):
        return ApiErrorCode.PIPELINE_CONFLICT
    if isinstance(exc, PipelineStageExecutionError):
        return _EXECUTION_REASON_TO_CODE.get(exc.reason_code, ApiErrorCode.INTERNAL_ERROR)
    if isinstance(exc, PipelineStagePersistenceError):
        reason = exc.reason_code
        if reason is PipelineFailureReason.REPOSITORY_UNAVAILABLE:
            return ApiErrorCode.REPOSITORY_UNAVAILABLE
        return ApiErrorCode.RESOURCE_CONFLICT
    return ApiErrorCode.INTERNAL_ERROR


def _retryable_for_orchestration(exc: PipelineOrchestrationError) -> bool:
    return exc.retry_classification is PipelineRetryClassification.RETRYABLE


def _make_error_response(
    error_code: ApiErrorCode,
    message: str,
    *,
    retryable: bool = False,
    stage: str | None = None,
) -> ApiErrorResponse:
    return ApiErrorResponse(
        error_code=error_code,
        message=message,
        retryable=retryable,
        stage=stage,
    )


def map_pipeline_error(exc: PipelineOrchestrationError) -> tuple[int, ApiErrorResponse]:
    """Map a pipeline orchestration exception to (HTTP status, ApiErrorResponse)."""
    if isinstance(exc, InvalidPipelineRequestError):
        code = _error_code_for_orchestration(exc)
        return 400, _make_error_response(code, "invalid pipeline request", stage=_stage(exc))
    if isinstance(exc, PipelinePrerequisiteError):
        code = _error_code_for_orchestration(exc)
        return 409, _make_error_response(code, "prerequisite not met", stage=_stage(exc))
    if isinstance(exc, PipelineConflictError):
        return 409, _make_error_response(
            ApiErrorCode.PIPELINE_CONFLICT, "pipeline conflict", stage=_stage(exc)
        )
    if isinstance(exc, (PipelineStageExecutionError, PipelineStagePersistenceError)):
        http_status = _http_status_for_orchestration(exc)
        code = _error_code_for_orchestration(exc)
        retryable = _retryable_for_orchestration(exc)
        return http_status, _make_error_response(
            code, "pipeline stage failed", retryable=retryable, stage=_stage(exc)
        )
    http_status = _http_status_for_orchestration(exc)
    code = _error_code_for_orchestration(exc)
    retryable = _retryable_for_orchestration(exc)
    return http_status, _make_error_response(
        code, "pipeline error", retryable=retryable, stage=_stage(exc)
    )


def _stage(exc: PipelineOrchestrationError) -> str | None:
    return exc.stage.value if exc.stage is not None else None


def register_exception_handlers(app: FastAPI) -> None:
    """Register all application-level exception handlers on the FastAPI app."""

    @app.exception_handler(RecordNotFoundError)
    async def _not_found(request: Request, exc: RecordNotFoundError) -> JSONResponse:
        body = _make_error_response(ApiErrorCode.RESOURCE_NOT_FOUND, "resource not found")
        return JSONResponse(status_code=404, content=body.model_dump())

    @app.exception_handler(RecordAlreadyExistsError)
    async def _already_exists(request: Request, exc: RecordAlreadyExistsError) -> JSONResponse:
        body = _make_error_response(ApiErrorCode.RESOURCE_CONFLICT, "resource conflict")
        return JSONResponse(status_code=409, content=body.model_dump())

    @app.exception_handler(StaleRecordVersionError)
    async def _stale(request: Request, exc: StaleRecordVersionError) -> JSONResponse:
        body = _make_error_response(ApiErrorCode.RESOURCE_CONFLICT, "stale revision")
        return JSONResponse(status_code=409, content=body.model_dump())

    @app.exception_handler(RepositoryUnavailableError)
    async def _repo_unavailable(request: Request, exc: RepositoryUnavailableError) -> JSONResponse:
        body = _make_error_response(
            ApiErrorCode.REPOSITORY_UNAVAILABLE, "repository unavailable", retryable=True
        )
        return JSONResponse(status_code=503, content=body.model_dump())

    @app.exception_handler(PipelineOrchestrationError)
    async def _pipeline_error(request: Request, exc: PipelineOrchestrationError) -> JSONResponse:
        http_status, body = map_pipeline_error(exc)
        return JSONResponse(status_code=http_status, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        field_errors = tuple(
            ApiErrorFieldError(
                field=".".join(str(loc) for loc in e["loc"]),
                message=e["msg"],
            )
            for e in exc.errors()
        )
        body = ApiErrorResponse(
            error_code=ApiErrorCode.INVALID_REQUEST,
            message="request validation failed",
            retryable=False,
            field_errors=field_errors,
        )
        return JSONResponse(status_code=422, content=body.model_dump())
