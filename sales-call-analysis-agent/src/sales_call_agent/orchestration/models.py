"""Immutable orchestration models, stage enums, and pipeline contracts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from sales_call_agent.persistence.keys import CallScoreKey, EvaluationKey
from sales_call_agent.speaker_identity.models import RoleEvidence

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_WARNING_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SEMVER_CORE_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class PipelineStage(StrEnum):
    """Canonical orchestrated pipeline stages in business order."""

    TRANSCRIPTION = "transcription"
    DIARIZATION = "diarization"
    ALIGNMENT = "alignment"
    ROLE_ASSIGNMENT = "role_assignment"
    EVALUATION = "evaluation"
    AGGREGATION = "aggregation"


CANONICAL_STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.TRANSCRIPTION,
    PipelineStage.DIARIZATION,
    PipelineStage.ALIGNMENT,
    PipelineStage.ROLE_ASSIGNMENT,
    PipelineStage.EVALUATION,
    PipelineStage.AGGREGATION,
)


class PipelineTarget(StrEnum):
    """Caller-selected last required orchestration stage."""

    ROLE_ASSIGNMENT = "role_assignment"
    EVALUATION = "evaluation"
    AGGREGATION = "aggregation"


class PipelineStageOutcomeStatus(StrEnum):
    """How a successful stage was satisfied."""

    EXECUTED = "executed"
    REUSED = "reused"
    RECONCILED = "reconciled"


class PipelineRunQualityFlag(StrEnum):
    """Quality conditions for a successful pipeline run."""

    PERSISTED_RESULTS_REUSED = "persisted_results_reused"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    LIMITED_COVERAGE = "limited_coverage"
    NO_SCORABLE_CRITERIA = "no_scorable_criteria"
    STATUS_REPAIRED = "status_repaired"
    CONCURRENT_RESULT_REUSED = "concurrent_result_reused"
    WARNINGS_PRESENT = "warnings_present"


class PipelineFailureReason(StrEnum):
    """Closed reason codes for orchestration failures."""

    INVALID_REQUEST = "invalid_request"
    MISSING_CALL = "missing_call"
    INVALID_CALL_STATUS = "invalid_call_status"
    MISSING_NORMALIZED_AUDIO = "missing_normalized_audio"
    RUBRIC_NOT_APPROVED = "rubric_not_approved"
    MISSING_RUBRIC = "missing_rubric"
    MISSING_PREREQUISITE = "missing_prerequisite"
    STATUS_ARTIFACT_INCONSISTENCY = "status_artifact_inconsistency"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_REQUEST_FAILED = "provider_request_failed"
    INVALID_PROVIDER_OUTPUT = "invalid_provider_output"
    UNSUPPORTED_CONFIGURATION = "unsupported_configuration"
    STAGE_EXECUTION_FAILED = "stage_execution_failed"
    PERSISTENCE_CONFLICT = "persistence_conflict"
    STALE_REVISION = "stale_revision"
    REPOSITORY_UNAVAILABLE = "repository_unavailable"
    MALFORMED_PERSISTED_DATA = "malformed_persisted_data"


class PipelineRetryClassification(StrEnum):
    """Retry guidance for orchestration failures."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    CONFLICT_RELOAD_REQUIRED = "conflict_reload_required"


def target_final_stage(target: PipelineTarget) -> PipelineStage:
    """Map a pipeline target to its final required stage."""
    if target is PipelineTarget.ROLE_ASSIGNMENT:
        return PipelineStage.ROLE_ASSIGNMENT
    if target is PipelineTarget.EVALUATION:
        return PipelineStage.EVALUATION
    return PipelineStage.AGGREGATION


def required_stages(target: PipelineTarget) -> tuple[PipelineStage, ...]:
    """Return the canonical required stage prefix for one target."""
    final = target_final_stage(target)
    stages: list[PipelineStage] = []
    for stage in CANONICAL_STAGE_ORDER:
        stages.append(stage)
        if stage is final:
            break
    return tuple(stages)


def _ensure_required_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and trimmed")


def _ensure_safe_identifier(value: object, field_name: str) -> None:
    _ensure_required_string(value, field_name)
    assert isinstance(value, str)
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a safe identifier")
    if "/" in value or "\\" in value or ":" in value:
        raise ValueError(f"{field_name} must not contain path-like characters")


def _ensure_semver(value: object, field_name: str) -> None:
    _ensure_required_string(value, field_name)
    assert isinstance(value, str)
    if not _SEMVER_CORE_RE.fullmatch(value):
        raise ValueError(f"{field_name} must match MAJOR.MINOR.PATCH")


def _ensure_safe_warning_code(value: object, field_name: str) -> None:
    _ensure_required_string(value, field_name)
    assert isinstance(value, str)
    if not _SAFE_WARNING_CODE_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a safe warning code")


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizedAudioReference:
    """Explicit already-normalized ASR artifact reference for orchestration."""

    storage_path: Path = field(repr=False)
    content_hash: str
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.storage_path, Path):
            raise ValueError("storage_path must be a Path")
        _ensure_required_string(self.content_hash, "content_hash")
        if self.duration_seconds is not None:
            if isinstance(self.duration_seconds, bool) or not isinstance(
                self.duration_seconds, int | float
            ):
                raise ValueError("duration_seconds must be a number")
            if not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0:
                raise ValueError("duration_seconds must be a finite positive number")


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineStageOutcome:
    """Outcome of one required stage in a successful pipeline run."""

    stage: PipelineStage
    status: PipelineStageOutcomeStatus
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stage, PipelineStage):
            raise ValueError("stage must be a PipelineStage")
        if not isinstance(self.status, PipelineStageOutcomeStatus):
            raise ValueError("status must be a PipelineStageOutcomeStatus")
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes")


@dataclass(frozen=True, slots=True, kw_only=True)
class RunCallPipelineRequest:
    """Business request to run or resume the call pipeline to a target stage."""

    call_id: str
    target: PipelineTarget = PipelineTarget.AGGREGATION
    role_evidence: tuple[RoleEvidence, ...] = ()
    rubric_id: str | None = None
    rubric_version: str | None = None
    normalized_audio: NormalizedAudioReference | None = None

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.call_id, "call_id")
        if not isinstance(self.target, PipelineTarget):
            raise ValueError("target must be a PipelineTarget")
        if not isinstance(self.role_evidence, tuple):
            raise ValueError("role_evidence must be a tuple")
        if self.normalized_audio is not None and not isinstance(
            self.normalized_audio, NormalizedAudioReference
        ):
            raise ValueError("normalized_audio must be a NormalizedAudioReference")

        needs_rubric = self.target in {
            PipelineTarget.EVALUATION,
            PipelineTarget.AGGREGATION,
        }
        if needs_rubric:
            if self.rubric_id is None or self.rubric_version is None:
                raise ValueError("rubric_id and rubric_version are required for this target")
            _ensure_safe_identifier(self.rubric_id, "rubric_id")
            _ensure_semver(self.rubric_version, "rubric_version")
        elif self.rubric_id is not None or self.rubric_version is not None:
            raise ValueError("rubric fields must be None for ROLE_ASSIGNMENT target")


@dataclass(frozen=True, slots=True, kw_only=True)
class RunCallPipelineResult:
    """Successful orchestration result that reached the requested target."""

    call_id: str
    requested_target: PipelineTarget
    reached_stage: PipelineStage
    stage_outcomes: tuple[PipelineStageOutcome, ...]
    evaluation_key: EvaluationKey | None = None
    call_score_key: CallScoreKey | None = None
    quality_flags: tuple[PipelineRunQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.call_id, "call_id")
        if not isinstance(self.requested_target, PipelineTarget):
            raise ValueError("requested_target must be a PipelineTarget")
        if not isinstance(self.reached_stage, PipelineStage):
            raise ValueError("reached_stage must be a PipelineStage")
        if self.reached_stage is not target_final_stage(self.requested_target):
            raise ValueError("reached_stage must match the requested target stage")

        expected = required_stages(self.requested_target)
        if len(self.stage_outcomes) != len(expected):
            raise ValueError("stage_outcomes must cover every required stage")
        for outcome, stage in zip(self.stage_outcomes, expected, strict=True):
            if not isinstance(outcome, PipelineStageOutcome):
                raise ValueError("stage_outcomes must contain PipelineStageOutcome values")
            if outcome.stage is not stage:
                raise ValueError("stage_outcomes must follow canonical required order")

        if self.requested_target is PipelineTarget.ROLE_ASSIGNMENT:
            if self.evaluation_key is not None or self.call_score_key is not None:
                raise ValueError(
                    "ROLE_ASSIGNMENT results must not include evaluation or score keys"
                )
        elif self.requested_target is PipelineTarget.EVALUATION:
            if self.evaluation_key is None:
                raise ValueError("EVALUATION results require evaluation_key")
            if self.call_score_key is not None:
                raise ValueError("EVALUATION results must not include call_score_key")
        else:
            if self.evaluation_key is None or self.call_score_key is None:
                raise ValueError("AGGREGATION results require evaluation_key and call_score_key")
            score_eval = getattr(self.call_score_key, "evaluation_key", None)
            if score_eval != self.evaluation_key:
                raise ValueError("call_score_key.evaluation_key must equal evaluation_key")

        for flag in self.quality_flags:
            if not isinstance(flag, PipelineRunQualityFlag):
                raise ValueError("quality_flags must contain PipelineRunQualityFlag values")
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes")
        has_warnings_flag = PipelineRunQualityFlag.WARNINGS_PRESENT in self.quality_flags
        if bool(self.warning_codes) != has_warnings_flag:
            raise ValueError("WARNINGS_PRESENT must match non-empty warning_codes")
