"""Evaluation and call-score response schemas (privacy-safe: no transcript text)."""

from __future__ import annotations

from sales_call_agent.api.schemas.common import StrictApiModel


class TranscriptEvidenceSpanResponse(StrictApiModel):
    """Transcript evidence span using segment/word indexes only (no text)."""

    source_segment_index: int
    source_word_start_index: int | None = None
    source_word_end_index: int | None = None
    speaker_label: str
    speaker_role: str
    warning_codes: tuple[str, ...] = ()


class AbsenceEvidenceResponse(StrictApiModel):
    """Structured absence evidence (timing and reviewed segment indexes only)."""

    scope_start_seconds: float
    scope_end_seconds: float
    speaker_role: str | None = None
    reason_code: str
    reviewed_segment_indexes: tuple[int, ...]
    warning_codes: tuple[str, ...] = ()


class CriterionEvaluationResponse(StrictApiModel):
    """Per-criterion evaluation result."""

    criterion_id: str
    status: str
    reason_code: str
    score: float | None = None
    score_level_label: str | None = None
    evidence_spans: tuple[TranscriptEvidenceSpanResponse, ...] = ()
    absence_evidence: AbsenceEvidenceResponse | None = None
    human_review_required: bool = False
    human_review_reason: str | None = None
    warning_codes: tuple[str, ...] = ()


class EvaluationResponse(StrictApiModel):
    """Full evaluation result response."""

    call_id: str
    rubric_id: str
    rubric_version: str
    provider_name: str
    model_name: str
    criterion_evaluations: tuple[CriterionEvaluationResponse, ...]
    quality_flags: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()


class CriterionScoreContributionResponse(StrictApiModel):
    """Per-criterion score contribution in a call-score result."""

    criterion_id: str
    criterion_weight: float
    status: str
    reason_code: str
    raw_score: float | None = None
    normalized_score: float | None = None
    weighted_points: float | None = None
    human_review_required: bool = False
    warning_codes: tuple[str, ...] = ()


class AggregationConfigResponse(StrictApiModel):
    """Applied aggregation policy (numeric config values as floats)."""

    minimum_scored_weight_coverage: float
    minimum_scored_criterion_coverage: float
    require_no_human_review_for_publish: bool


class CallScoreResponse(StrictApiModel):
    """Full call-score result response."""

    call_id: str
    rubric_id: str
    rubric_version: str
    aggregation_policy_fingerprint: str
    criterion_contributions: tuple[CriterionScoreContributionResponse, ...]
    weighted_performance_score: float | None = None
    scored_weight_coverage: float | None = None
    scored_criterion_coverage: float | None = None
    publication_status: str
    quality_flags: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    applied_config: AggregationConfigResponse
