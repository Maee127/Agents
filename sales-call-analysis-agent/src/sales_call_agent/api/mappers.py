"""Explicit mapper functions between domain/orchestration models and API DTOs.

These pure functions are the only place that translates domain internals to API
schemas. Routes must never use asdict(), generic dataclass dumping, or
Pydantic auto-validation over domain objects.
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from sales_call_agent.aggregation.models import CallScoreResult
from sales_call_agent.api.schemas.calls import CallCreateRequest, CallResponse
from sales_call_agent.api.schemas.pipeline import (
    CallScoreKeyResponse,
    EvaluationKeyResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStageOutcomeResponse,
    RoleEvidenceRequest,
)
from sales_call_agent.api.schemas.results import (
    AbsenceEvidenceResponse,
    AggregationConfigResponse,
    CallScoreResponse,
    CriterionEvaluationResponse,
    CriterionScoreContributionResponse,
    EvaluationResponse,
    TranscriptEvidenceSpanResponse,
)
from sales_call_agent.api.schemas.rubrics import RubricRevisionSummary
from sales_call_agent.domain.models import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    SourceType,
)
from sales_call_agent.evaluation.models import (
    AbsenceEvidence,
    CallEvaluationResult,
    CriterionEvaluation,
    TranscriptEvidenceSpan,
)
from sales_call_agent.orchestration.models import (
    NormalizedAudioReference,
    PipelineTarget,
    RunCallPipelineRequest,
    RunCallPipelineResult,
)
from sales_call_agent.persistence.keys import (
    EvaluationKey,
    aggregation_policy_fingerprint,
)
from sales_call_agent.persistence.records import VersionedCallRecord, VersionedRubricRecord
from sales_call_agent.speaker_identity.models import (
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)


def call_create_request_to_domain(req: CallCreateRequest) -> Call:
    """Map a CallCreateRequest to a new Call domain aggregate (status=RECEIVED).

    The storage reference is extracted from SecretStr exactly once here for
    domain construction; it never appears in responses or repr.
    """
    storage_path = req.original_audio_storage_ref.get_secret_value()
    metadata = CallMetadata(
        call_id=req.call_id,
        seller_number=req.seller_number,
        source_type=SourceType(req.source_type),
        call_timestamp=req.call_timestamp.astimezone(UTC),
        duration_seconds=req.duration_seconds,
        counterparty_phone=req.counterparty_phone,
        original_filename=req.original_filename,
        audio_channels=AudioChannels(req.audio_channels),
        storage_path=storage_path,
    )
    audio = AudioAsset(
        storage_path=storage_path,
        audio_channels=AudioChannels(req.audio_channels),
        content_hash=req.original_audio_content_hash,
    )
    return Call(metadata=metadata, audio=audio, status=CallProcessingStatus.RECEIVED)


def versioned_call_to_response(
    record: VersionedCallRecord,
    *,
    has_transcription: bool = False,
    has_diarization: bool = False,
    has_alignment: bool = False,
    has_role_assignment: bool = False,
) -> CallResponse:
    """Map a VersionedCallRecord to a privacy-safe CallResponse."""
    call = record.value
    return CallResponse(
        call_id=call.call_id,
        status=call.status.value,
        revision=record.revision,
        source_type=call.metadata.source_type.value,
        audio_channels=call.metadata.audio_channels.value,
        duration_seconds=call.metadata.duration_seconds,
        has_transcription=has_transcription,
        has_diarization=has_diarization,
        has_alignment=has_alignment,
        has_role_assignment=has_role_assignment,
    )


def _map_role_evidence(req: RoleEvidenceRequest) -> RoleEvidence:
    return RoleEvidence(
        evidence_id=req.evidence_id,
        speaker_label=req.speaker_label,
        evidence_type=RoleEvidenceType(req.evidence_type),
        suggested_role=SpeakerRole(req.suggested_role),
    )


def pipeline_run_request_to_domain(req: PipelineRunRequest) -> RunCallPipelineRequest:
    """Map a PipelineRunRequest to an orchestration RunCallPipelineRequest."""
    normalized_audio: NormalizedAudioReference | None = None
    if req.normalized_audio is not None:
        na = req.normalized_audio
        normalized_audio = NormalizedAudioReference(
            storage_path=Path(na.storage_ref.get_secret_value()),
            content_hash=na.content_hash,
            duration_seconds=na.duration_seconds,
        )
    return RunCallPipelineRequest(
        call_id=req.call_id,
        target=PipelineTarget(req.target),
        rubric_id=req.rubric_id,
        rubric_version=req.rubric_version,
        role_evidence=tuple(_map_role_evidence(e) for e in req.role_evidence),
        normalized_audio=normalized_audio,
    )


def pipeline_result_to_response(result: RunCallPipelineResult) -> PipelineRunResponse:
    """Map a RunCallPipelineResult to a PipelineRunResponse."""
    evaluation_key: EvaluationKeyResponse | None = None
    if result.evaluation_key is not None:
        ek = result.evaluation_key
        evaluation_key = EvaluationKeyResponse(
            call_id=ek.call_id,
            rubric_id=ek.rubric_id,
            rubric_version=ek.rubric_version,
            provider_name=ek.provider_name,
            model_name=ek.model_name,
        )
    call_score_key: CallScoreKeyResponse | None = None
    if result.call_score_key is not None:
        csk = result.call_score_key
        call_score_key = CallScoreKeyResponse(
            call_id=csk.evaluation_key.call_id,
            rubric_id=csk.evaluation_key.rubric_id,
            rubric_version=csk.evaluation_key.rubric_version,
            provider_name=csk.evaluation_key.provider_name,
            model_name=csk.evaluation_key.model_name,
            aggregation_policy_fingerprint=csk.aggregation_policy_fingerprint,
        )
    return PipelineRunResponse(
        call_id=result.call_id,
        requested_target=result.requested_target.value,
        reached_stage=result.reached_stage.value,
        stage_outcomes=tuple(
            PipelineStageOutcomeResponse(
                stage=o.stage.value,
                status=o.status.value,
                warning_codes=o.warning_codes,
            )
            for o in result.stage_outcomes
        ),
        evaluation_key=evaluation_key,
        call_score_key=call_score_key,
        quality_flags=tuple(f.value for f in result.quality_flags),
        warning_codes=result.warning_codes,
    )


def _map_evidence_span(span: TranscriptEvidenceSpan) -> TranscriptEvidenceSpanResponse:
    return TranscriptEvidenceSpanResponse(
        source_segment_index=span.source_segment_index,
        source_word_start_index=span.source_word_start_index,
        source_word_end_index=span.source_word_end_index,
        speaker_label=span.speaker_label,
        speaker_role=span.speaker_role.value,
        warning_codes=span.warning_codes,
    )


def _map_absence_evidence(ev: AbsenceEvidence) -> AbsenceEvidenceResponse:
    return AbsenceEvidenceResponse(
        scope_start_seconds=ev.scope_start_seconds,
        scope_end_seconds=ev.scope_end_seconds,
        speaker_role=ev.speaker_role.value if ev.speaker_role is not None else None,
        reason_code=ev.reason_code.value,
        reviewed_segment_indexes=ev.reviewed_segment_indexes,
        warning_codes=ev.warning_codes,
    )


def _map_criterion_evaluation(ce: CriterionEvaluation) -> CriterionEvaluationResponse:
    return CriterionEvaluationResponse(
        criterion_id=ce.criterion_id,
        status=ce.status.value,
        reason_code=ce.reason_code.value,
        score=ce.score,
        score_level_label=ce.score_level_label,
        evidence_spans=tuple(_map_evidence_span(s) for s in ce.evidence_spans),
        absence_evidence=(
            _map_absence_evidence(ce.absence_evidence) if ce.absence_evidence is not None else None
        ),
        human_review_required=ce.human_review_required,
        human_review_reason=(
            ce.human_review_reason.value if ce.human_review_reason is not None else None
        ),
        warning_codes=ce.warning_codes,
    )


def evaluation_to_response(result: CallEvaluationResult) -> EvaluationResponse:
    """Map a CallEvaluationResult to an EvaluationResponse."""
    return EvaluationResponse(
        call_id=result.call_id,
        rubric_id=result.rubric_id,
        rubric_version=result.rubric_version,
        provider_name=result.provider_name,
        model_name=result.model_name,
        criterion_evaluations=tuple(
            _map_criterion_evaluation(ce) for ce in result.criterion_evaluations
        ),
        quality_flags=tuple(f.value for f in result.quality_flags),
        warning_codes=result.warning_codes,
    )


def call_score_to_response(
    result: CallScoreResult,
    *,
    evaluation_key: EvaluationKey,
) -> CallScoreResponse:
    """Map a CallScoreResult to a CallScoreResponse."""
    fingerprint = aggregation_policy_fingerprint(result.config)
    config_resp = AggregationConfigResponse(
        minimum_scored_weight_coverage=float(result.config.minimum_scored_weight_coverage),
        minimum_scored_criterion_coverage=float(result.config.minimum_scored_criterion_coverage),
        require_no_human_review_for_publish=result.config.require_no_human_review_for_publish,
    )
    return CallScoreResponse(
        call_id=result.call_id,
        rubric_id=result.rubric_id,
        rubric_version=result.rubric_version,
        aggregation_policy_fingerprint=fingerprint,
        criterion_contributions=tuple(
            CriterionScoreContributionResponse(
                criterion_id=c.criterion_id,
                criterion_weight=c.criterion_weight,
                status=c.status.value,
                reason_code=c.reason_code.value,
                raw_score=c.raw_score,
                normalized_score=c.normalized_score,
                weighted_points=c.weighted_points,
                human_review_required=c.human_review_required,
                warning_codes=c.warning_codes,
            )
            for c in result.criterion_contributions
        ),
        weighted_performance_score=result.weighted_performance_score,
        scored_weight_coverage=result.scored_weight_coverage,
        scored_criterion_coverage=result.scored_criterion_coverage,
        publication_status=result.publication_status.value,
        quality_flags=tuple(f.value for f in result.quality_flags),
        warning_codes=result.warning_codes,
        applied_config=config_resp,
    )


def versioned_rubric_to_summary(record: VersionedRubricRecord) -> RubricRevisionSummary:
    """Map a VersionedRubricRecord to a privacy-safe RubricRevisionSummary."""
    rubric = record.value
    source_ids = tuple(
        sorted(
            {
                citation.source_id
                for criterion in rubric.criteria
                for citation in criterion.source_citations
            }
        )
    )
    return RubricRevisionSummary(
        rubric_id=rubric.rubric_id,
        version=rubric.version,
        status=rubric.status.value,
        revision=record.revision,
        criterion_ids=tuple(c.criterion_id for c in rubric.criteria),
        source_ids=source_ids,
        language=rubric.language,
    )
