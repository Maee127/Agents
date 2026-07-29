"""Pipeline run request and response schemas."""

from __future__ import annotations

from pydantic import SecretStr, field_validator

from sales_call_agent.api.schemas.common import (
    RequestApiModel,
    StrictApiModel,
    validate_safe_identifier,
)


class NormalizedAudioReferenceRequest(RequestApiModel):
    """Normalized-audio metadata sent with a pipeline run request.

    storage_ref is SecretStr: never echoed in validation errors, repr, or
    exception messages. The mapper extracts the value once to construct a Path.
    """

    storage_ref: SecretStr
    content_hash: str
    duration_seconds: float | None = None


class RoleEvidenceRequest(RequestApiModel):
    """Single role-evidence entry for speaker identity hints."""

    evidence_id: str
    speaker_label: str
    evidence_type: str
    suggested_role: str

    @field_validator("evidence_id")
    @classmethod
    def _validate_evidence_id(cls, v: str) -> str:
        return validate_safe_identifier(v)


class PipelineRunRequest(RequestApiModel):
    """Request body for POST /api/v1/pipeline-runs.

    Provider and model identities are NOT accepted here.  Providers are
    selected by the server-side PipelineDependencies configuration, not
    by API callers.
    """

    call_id: str
    target: str = "aggregation"
    rubric_id: str | None = None
    rubric_version: str | None = None
    role_evidence: tuple[RoleEvidenceRequest, ...] = ()
    normalized_audio: NormalizedAudioReferenceRequest | None = None

    @field_validator("call_id")
    @classmethod
    def _validate_call_id(cls, v: str) -> str:
        return validate_safe_identifier(v)


class PipelineStageOutcomeResponse(StrictApiModel):
    """Outcome for one stage in the pipeline run response."""

    stage: str
    status: str
    warning_codes: tuple[str, ...] = ()


class EvaluationKeyResponse(StrictApiModel):
    """Evaluation identity included in a pipeline run response.

    provider_name and model_name are internal operational identifiers used
    only to retrieve an existing result.  They are not caller-controlled
    provider selection parameters.
    """

    call_id: str
    rubric_id: str
    rubric_version: str
    provider_name: str
    model_name: str


class CallScoreKeyResponse(StrictApiModel):
    """Call-score identity included in a pipeline run response."""

    call_id: str
    rubric_id: str
    rubric_version: str
    provider_name: str
    model_name: str
    aggregation_policy_fingerprint: str


class PipelineRunResponse(StrictApiModel):
    """Response for POST /api/v1/pipeline-runs."""

    call_id: str
    requested_target: str
    reached_stage: str
    stage_outcomes: tuple[PipelineStageOutcomeResponse, ...]
    evaluation_key: EvaluationKeyResponse | None = None
    call_score_key: CallScoreKeyResponse | None = None
    quality_flags: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
