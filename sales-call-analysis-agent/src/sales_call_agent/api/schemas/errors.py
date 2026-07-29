"""Stable error schema and error code enum for the v1 API."""

from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict

from sales_call_agent.api.schemas.common import StrictApiModel


class ApiErrorCode(StrEnum):
    """Closed set of stable machine-readable error codes."""

    INVALID_REQUEST = "invalid_request"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_CONFLICT = "resource_conflict"
    PREREQUISITE_NOT_MET = "prerequisite_not_met"
    RUBRIC_NOT_APPROVED = "rubric_not_approved"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RESPONSE_INVALID = "provider_response_invalid"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"
    PIPELINE_CONFLICT = "pipeline_conflict"
    INTERNAL_ERROR = "internal_error"


class ApiErrorFieldError(StrictApiModel):
    """Single field-level validation error entry."""

    field: str
    message: str


class ApiErrorResponse(StrictApiModel):
    """Stable error envelope returned for all non-2xx responses."""

    model_config = ConfigDict(strict=True, extra="forbid")

    error_code: ApiErrorCode
    message: str
    retryable: bool
    stage: str | None = None
    field_errors: tuple[ApiErrorFieldError, ...] = ()
