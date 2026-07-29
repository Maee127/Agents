"""Deterministic, checkpoint-aware orchestration for one call pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from sales_call_agent.aggregation.engine import aggregate_call_evaluation
from sales_call_agent.aggregation.models import AggregationRequest, CallScoreResult
from sales_call_agent.alignment.engine import align_transcript_with_speakers
from sales_call_agent.alignment.models import AlignmentRequest, AlignmentResult
from sales_call_agent.diarization.exceptions import (
    DiarizationProviderUnavailableError,
    DiarizationRequestFailedError,
    DiarizationTimeoutError,
)
from sales_call_agent.diarization.models import DiarizationRequest, DiarizationResult
from sales_call_agent.diarization.provider import run_diarization
from sales_call_agent.domain.exceptions import DomainError
from sales_call_agent.domain.models import CallProcessingStatus
from sales_call_agent.evaluation.exceptions import (
    EvaluationProviderUnavailableError,
    EvaluationRequestFailedError,
    EvaluationTimeoutError,
)
from sales_call_agent.evaluation.models import CallEvaluationResult, EvaluationRequest
from sales_call_agent.evaluation.provider import run_evaluation
from sales_call_agent.knowledge.models import RubricStatus, SalesRubric
from sales_call_agent.orchestration.dependencies import PipelineDependencies
from sales_call_agent.orchestration.exceptions import (
    InvalidPipelineRequestError,
    PipelineConflictError,
    PipelineOrchestrationError,
    PipelinePrerequisiteError,
    PipelineStageExecutionError,
    PipelineStagePersistenceError,
)
from sales_call_agent.orchestration.models import (
    NormalizedAudioReference,
    PipelineFailureReason,
    PipelineRetryClassification,
    PipelineRunQualityFlag,
    PipelineStage,
    PipelineStageOutcome,
    PipelineStageOutcomeStatus,
    PipelineTarget,
    RunCallPipelineRequest,
    RunCallPipelineResult,
    required_stages,
    target_final_stage,
)
from sales_call_agent.persistence.exceptions import (
    RecordAlreadyExistsError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleRecordVersionError,
)
from sales_call_agent.persistence.keys import (
    CallScoreKey,
    EvaluationKey,
    aggregation_policy_fingerprint,
)
from sales_call_agent.persistence.records import VersionedCallRecord
from sales_call_agent.persistence.unit_of_work import UnitOfWork
from sales_call_agent.speaker_identity.engine import assign_speaker_roles
from sales_call_agent.speaker_identity.models import RoleAssignmentRequest, RoleAssignmentResult
from sales_call_agent.transcription.exceptions import (
    TranscriptionProviderUnavailableError,
    TranscriptionRequestFailedError,
    TranscriptionTimeoutError,
)
from sales_call_agent.transcription.models import TranscriptionRequest, TranscriptionResult
from sales_call_agent.transcription.provider import run_transcription

TRANSCRIPTION_COMPATIBLE = frozenset(
    {
        CallProcessingStatus.TRANSCRIBED,
        CallProcessingStatus.DIARIZED,
        CallProcessingStatus.ROLES_ASSIGNED,
        CallProcessingStatus.EVALUATED,
    }
)
DIARIZATION_COMPATIBLE = frozenset(
    {
        CallProcessingStatus.DIARIZED,
        CallProcessingStatus.ROLES_ASSIGNED,
        CallProcessingStatus.EVALUATED,
    }
)
ROLE_COMPATIBLE = frozenset({CallProcessingStatus.ROLES_ASSIGNED, CallProcessingStatus.EVALUATED})
EVALUATION_COMPATIBLE = frozenset({CallProcessingStatus.EVALUATED})
_MAX_CONFLICT_RECONCILIATIONS = 2


@dataclass(slots=True)
class _Artifacts:
    transcription: TranscriptionResult | None = None
    diarization: DiarizationResult | None = None
    alignment: AlignmentResult | None = None
    roles: RoleAssignmentResult | None = None
    rubric: SalesRubric | None = None
    evaluation: CallEvaluationResult | None = None
    evaluation_key: EvaluationKey | None = None
    score: CallScoreResult | None = None
    score_key: CallScoreKey | None = None


@dataclass(frozen=True, slots=True)
class _FixedEvaluationProvider:
    """Provider facade used to validate a persisted evaluation at its boundary."""

    result: CallEvaluationResult

    @property
    def provider_name(self) -> str:
        return self.result.provider_name

    @property
    def model_name(self) -> str:
        return self.result.model_name

    def evaluate(self, request: EvaluationRequest) -> CallEvaluationResult:
        return self.result


def run_call_pipeline(
    request: RunCallPipelineRequest,
    dependencies: PipelineDependencies,
) -> RunCallPipelineResult:
    """Run or resume the requested deterministic pipeline prefix."""
    if not isinstance(request, RunCallPipelineRequest):
        raise _invalid_request("request must be a RunCallPipelineRequest")
    if not isinstance(dependencies, PipelineDependencies):
        raise _invalid_request("dependencies must be a PipelineDependencies")

    flags: set[PipelineRunQualityFlag] = set()
    outcomes: list[PipelineStageOutcome] = []
    artifacts = _load_initial(request, dependencies)

    for stage in required_stages(request.target):
        try:
            outcome, repaired = _run_stage(stage, request, dependencies, artifacts)
        except PipelineStageExecutionError as error:
            if error.retry_classification is PipelineRetryClassification.NON_RETRYABLE:
                _persist_failure_status(request.call_id, stage, dependencies)
            raise
        outcomes.append(outcome)
        if repaired:
            flags.add(PipelineRunQualityFlag.STATUS_REPAIRED)
        if outcome.status is PipelineStageOutcomeStatus.REUSED:
            flags.add(PipelineRunQualityFlag.PERSISTED_RESULTS_REUSED)
        if outcome.status is PipelineStageOutcomeStatus.RECONCILED:
            flags.add(PipelineRunQualityFlag.CONCURRENT_RESULT_REUSED)

    warning_codes = _warning_codes_from_outcomes(outcomes)
    if warning_codes:
        flags.add(PipelineRunQualityFlag.WARNINGS_PRESENT)
    _add_target_quality_flags(flags, request.target, artifacts)
    return RunCallPipelineResult(
        call_id=request.call_id,
        requested_target=request.target,
        reached_stage=target_final_stage(request.target),
        stage_outcomes=tuple(outcomes),
        evaluation_key=(
            artifacts.evaluation_key
            if request.target is not PipelineTarget.ROLE_ASSIGNMENT
            else None
        ),
        call_score_key=(
            artifacts.score_key if request.target is PipelineTarget.AGGREGATION else None
        ),
        quality_flags=tuple(flag for flag in PipelineRunQualityFlag if flag in flags),
        warning_codes=warning_codes,
    )


def _load_initial(
    request: RunCallPipelineRequest, dependencies: PipelineDependencies
) -> _Artifacts:
    uow = dependencies.unit_of_work_factory()
    try:
        call = uow.calls.find(request.call_id)
        if call is None:
            raise PipelinePrerequisiteError(
                "call does not exist",
                reason_code=PipelineFailureReason.MISSING_CALL,
                retry_classification=PipelineRetryClassification.NON_RETRYABLE,
            )
        if call.value.status in {
            CallProcessingStatus.RECEIVED,
            CallProcessingStatus.REJECTED,
            CallProcessingStatus.FAILED,
        }:
            raise InvalidPipelineRequestError(
                "call status cannot be orchestrated",
                reason_code=PipelineFailureReason.INVALID_CALL_STATUS,
                retry_classification=PipelineRetryClassification.NON_RETRYABLE,
            )
        artifacts = _Artifacts(
            transcription=uow.processing_results.find_transcription(request.call_id),
            diarization=uow.processing_results.find_diarization(request.call_id),
            alignment=uow.processing_results.find_alignment(request.call_id),
            roles=uow.processing_results.find_role_assignment(request.call_id),
        )
        if request.target is not PipelineTarget.ROLE_ASSIGNMENT:
            assert request.rubric_id is not None and request.rubric_version is not None
            rubric = uow.rubrics.find(request.rubric_id, request.rubric_version)
            if rubric is None:
                raise PipelinePrerequisiteError(
                    "rubric does not exist",
                    reason_code=PipelineFailureReason.MISSING_RUBRIC,
                    retry_classification=PipelineRetryClassification.NON_RETRYABLE,
                )
            if rubric.value.status is not RubricStatus.APPROVED:
                raise PipelinePrerequisiteError(
                    "rubric is not approved",
                    reason_code=PipelineFailureReason.RUBRIC_NOT_APPROVED,
                    retry_classification=PipelineRetryClassification.NON_RETRYABLE,
                )
            artifacts.rubric = rubric.value
    except RepositoryUnavailableError as error:
        raise _persistence_error(error, PipelineStage.TRANSCRIPTION) from error
    finally:
        uow.rollback()
    return artifacts


def _run_stage(
    stage: PipelineStage,
    request: RunCallPipelineRequest,
    dependencies: PipelineDependencies,
    artifacts: _Artifacts,
) -> tuple[PipelineStageOutcome, bool]:
    if stage is PipelineStage.TRANSCRIPTION:
        return _transcription(request, dependencies, artifacts)
    if stage is PipelineStage.DIARIZATION:
        return _diarization(request, dependencies, artifacts)
    if stage is PipelineStage.ALIGNMENT:
        return _alignment(request, dependencies, artifacts)
    if stage is PipelineStage.ROLE_ASSIGNMENT:
        return _roles(request, dependencies, artifacts)
    if stage is PipelineStage.EVALUATION:
        return _evaluation(request, dependencies, artifacts)
    return _aggregation(request, dependencies, artifacts)


def _transcription(
    request: RunCallPipelineRequest, deps: PipelineDependencies, a: _Artifacts
) -> tuple[PipelineStageOutcome, bool]:
    if a.transcription is not None:
        return _reuse_with_repair(
            request.call_id,
            PipelineStage.TRANSCRIPTION,
            TRANSCRIPTION_COMPATIBLE,
            deps,
            warning_codes=a.transcription.warning_codes,
        )
    audio = _required_audio(request, PipelineStage.TRANSCRIPTION)
    result = _provider_call(
        PipelineStage.TRANSCRIPTION,
        lambda: run_transcription(
            deps.transcription_provider,
            TranscriptionRequest(
                call_id=request.call_id,
                normalized_audio_path=str(audio.storage_path),
                normalized_audio_hash=audio.content_hash,
                expected_language=deps.transcription_expected_language,
                provider_config_id=deps.transcription_provider_config_id,
            ),
        ),
    )
    assert isinstance(result, TranscriptionResult)
    outcome, repaired = _persist_stage(request.call_id, PipelineStage.TRANSCRIPTION, result, deps)
    a.transcription = result
    return outcome, repaired


def _diarization(
    request: RunCallPipelineRequest, deps: PipelineDependencies, a: _Artifacts
) -> tuple[PipelineStageOutcome, bool]:
    if a.diarization is not None:
        return _reuse_with_repair(
            request.call_id,
            PipelineStage.DIARIZATION,
            DIARIZATION_COMPATIBLE,
            deps,
            warning_codes=a.diarization.warning_codes,
        )
    audio = _required_audio(request, PipelineStage.DIARIZATION)
    result = _provider_call(
        PipelineStage.DIARIZATION,
        lambda: run_diarization(
            deps.diarization_provider,
            DiarizationRequest(
                call_id=request.call_id,
                normalized_audio_path=str(audio.storage_path),
                normalized_audio_hash=audio.content_hash,
                audio_duration_seconds=audio.duration_seconds,
                provider_config_id=deps.diarization_provider_config_id,
            ),
        ),
    )
    assert isinstance(result, DiarizationResult)
    outcome, repaired = _persist_stage(request.call_id, PipelineStage.DIARIZATION, result, deps)
    a.diarization = result
    return outcome, repaired


def _alignment(
    request: RunCallPipelineRequest, deps: PipelineDependencies, a: _Artifacts
) -> tuple[PipelineStageOutcome, bool]:
    if a.alignment is not None:
        return _reuse_with_repair(
            request.call_id,
            PipelineStage.ALIGNMENT,
            DIARIZATION_COMPATIBLE,
            deps,
            warning_codes=a.alignment.warning_codes,
        )
    if a.transcription is None or a.diarization is None:
        raise _missing(PipelineStage.ALIGNMENT)
    result = _provider_call(
        PipelineStage.ALIGNMENT,
        lambda: align_transcript_with_speakers(
            AlignmentRequest(
                call_id=request.call_id,
                transcription=a.transcription,
                diarization=a.diarization,
                config=deps.alignment_config,
            )
        ),
    )
    assert isinstance(result, AlignmentResult)
    outcome, repaired = _persist_stage(request.call_id, PipelineStage.ALIGNMENT, result, deps)
    a.alignment = result
    return outcome, repaired


def _roles(
    request: RunCallPipelineRequest, deps: PipelineDependencies, a: _Artifacts
) -> tuple[PipelineStageOutcome, bool]:
    if a.roles is not None:
        return _reuse_with_repair(
            request.call_id,
            PipelineStage.ROLE_ASSIGNMENT,
            ROLE_COMPATIBLE,
            deps,
            warning_codes=a.roles.warning_codes,
        )
    if a.alignment is None:
        raise _missing(PipelineStage.ROLE_ASSIGNMENT)
    result = _provider_call(
        PipelineStage.ROLE_ASSIGNMENT,
        lambda: assign_speaker_roles(
            RoleAssignmentRequest(
                call_id=request.call_id,
                alignment=a.alignment,
                evidence=request.role_evidence,
                config=deps.role_assignment_config,
            )
        ),
    )
    assert isinstance(result, RoleAssignmentResult)
    outcome, repaired = _persist_stage(request.call_id, PipelineStage.ROLE_ASSIGNMENT, result, deps)
    a.roles = result
    return outcome, repaired


def _evaluation(
    request: RunCallPipelineRequest, deps: PipelineDependencies, a: _Artifacts
) -> tuple[PipelineStageOutcome, bool]:
    if a.alignment is None or a.roles is None or a.rubric is None:
        raise _missing(PipelineStage.EVALUATION)
    expected_key = _expected_evaluation_key(request, deps)
    a.evaluation_key = expected_key
    existing = _find_evaluation_by_key(deps, expected_key)
    eval_request = EvaluationRequest(
        call_id=request.call_id,
        alignment=a.alignment,
        role_assignment=a.roles,
        rubric=a.rubric,
        provider_config_id=deps.evaluation_provider_config_id,
    )
    if existing is not None:
        _provider_call(
            PipelineStage.EVALUATION,
            lambda: run_evaluation(_FixedEvaluationProvider(existing), eval_request),
        )
        a.evaluation = existing
        return _reuse_with_repair(
            request.call_id,
            PipelineStage.EVALUATION,
            EVALUATION_COMPATIBLE,
            deps,
            warning_codes=existing.warning_codes,
        )
    result = _provider_call(
        PipelineStage.EVALUATION,
        lambda: run_evaluation(deps.evaluation_provider, eval_request),
    )
    assert isinstance(result, CallEvaluationResult)
    outcome, repaired = _persist_stage(request.call_id, PipelineStage.EVALUATION, result, deps)
    a.evaluation = result
    return outcome, repaired


def _aggregation(
    request: RunCallPipelineRequest, deps: PipelineDependencies, a: _Artifacts
) -> tuple[PipelineStageOutcome, bool]:
    if a.evaluation is None or a.evaluation_key is None or a.rubric is None:
        raise _missing(PipelineStage.AGGREGATION)
    key = CallScoreKey(
        evaluation_key=a.evaluation_key,
        aggregation_policy_fingerprint=aggregation_policy_fingerprint(deps.aggregation_config),
    )
    uow = deps.unit_of_work_factory()
    try:
        existing = uow.call_scores.find(key)
    finally:
        uow.rollback()
    if existing is not None:
        _validate_score(existing, a.rubric, a.evaluation, deps)
        a.score, a.score_key = existing, key
        return (
            PipelineStageOutcome(
                stage=PipelineStage.AGGREGATION,
                status=PipelineStageOutcomeStatus.REUSED,
                warning_codes=existing.warning_codes,
            ),
            False,
        )
    result = _provider_call(
        PipelineStage.AGGREGATION,
        lambda: aggregate_call_evaluation(
            AggregationRequest(
                call_id=request.call_id,
                rubric=a.rubric,
                evaluation=a.evaluation,
                config=deps.aggregation_config,
            )
        ),
    )
    assert isinstance(result, CallScoreResult)
    outcome, repaired = _persist_stage(
        request.call_id, PipelineStage.AGGREGATION, result, deps, evaluation_key=a.evaluation_key
    )
    a.score, a.score_key = result, key
    return outcome, repaired


def _persist_stage(
    call_id: str,
    stage: PipelineStage,
    result: object,
    deps: PipelineDependencies,
    *,
    evaluation_key: EvaluationKey | None = None,
) -> tuple[PipelineStageOutcome, bool]:
    warning_codes = tuple(getattr(result, "warning_codes", ()))
    for attempt in range(_MAX_CONFLICT_RECONCILIATIONS + 1):
        uow = deps.unit_of_work_factory()
        try:
            record = uow.calls.get(call_id)
            _add_result(uow, stage, result, evaluation_key)
            repaired = _advance_if_needed(uow, record, stage)
            uow.commit()
            return (
                PipelineStageOutcome(
                    stage=stage,
                    status=PipelineStageOutcomeStatus.EXECUTED,
                    warning_codes=warning_codes,
                ),
                repaired,
            )
        except (RecordAlreadyExistsError, StaleRecordVersionError):
            uow.rollback()
            if attempt == _MAX_CONFLICT_RECONCILIATIONS:
                raise PipelineConflictError(
                    "concurrent persistence conflict",
                    stage=stage,
                    reason_code=PipelineFailureReason.PERSISTENCE_CONFLICT,
                    retry_classification=PipelineRetryClassification.NON_RETRYABLE,
                ) from None
            if _result_exists(call_id, stage, deps, evaluation_key):
                repaired = _repair_status(call_id, stage, deps)
                return (
                    PipelineStageOutcome(
                        stage=stage,
                        status=PipelineStageOutcomeStatus.RECONCILED,
                        warning_codes=warning_codes,
                    ),
                    repaired,
                )
        except RepositoryUnavailableError as error:
            raise _persistence_error(error, stage) from error
        except RecordNotFoundError as error:
            raise PipelinePrerequisiteError(
                "persistence prerequisite missing",
                stage=stage,
                reason_code=PipelineFailureReason.MISSING_PREREQUISITE,
                retry_classification=PipelineRetryClassification.NON_RETRYABLE,
            ) from error
        finally:
            uow.rollback()
    raise AssertionError("unreachable")


def _add_result(
    uow: UnitOfWork,
    stage: PipelineStage,
    result: object,
    evaluation_key: EvaluationKey | None,
) -> None:
    processing = uow.processing_results
    if stage is PipelineStage.TRANSCRIPTION:
        assert isinstance(result, TranscriptionResult)
        processing.add_transcription(result)
    elif stage is PipelineStage.DIARIZATION:
        assert isinstance(result, DiarizationResult)
        processing.add_diarization(result)
    elif stage is PipelineStage.ALIGNMENT:
        assert isinstance(result, AlignmentResult)
        processing.add_alignment(result)
    elif stage is PipelineStage.ROLE_ASSIGNMENT:
        assert isinstance(result, RoleAssignmentResult)
        processing.add_role_assignment(result)
    elif stage is PipelineStage.EVALUATION:
        assert isinstance(result, CallEvaluationResult)
        uow.evaluations.add(result)
    else:
        assert evaluation_key is not None
        assert isinstance(result, CallScoreResult)
        uow.call_scores.add(result, evaluation_key=evaluation_key)


def _reuse_with_repair(
    call_id: str,
    stage: PipelineStage,
    compatible: frozenset[CallProcessingStatus],
    deps: PipelineDependencies,
    *,
    warning_codes: tuple[str, ...] = (),
) -> tuple[PipelineStageOutcome, bool]:
    return (
        PipelineStageOutcome(
            stage=stage,
            status=PipelineStageOutcomeStatus.REUSED,
            warning_codes=warning_codes,
        ),
        _repair_status(call_id, stage, deps, compatible),
    )


def _repair_status(
    call_id: str,
    stage: PipelineStage,
    deps: PipelineDependencies,
    compatible: frozenset[CallProcessingStatus] | None = None,
) -> bool:
    compatible = compatible or _compatible_statuses(stage)
    uow = deps.unit_of_work_factory()
    try:
        record = uow.calls.get(call_id)
        if record.value.status in compatible:
            return False
        if not _complete_chain(uow, call_id, stage):
            raise PipelinePrerequisiteError(
                "status repair requires a complete artifact chain",
                stage=stage,
                reason_code=PipelineFailureReason.STATUS_ARTIFACT_INCONSISTENCY,
                retry_classification=PipelineRetryClassification.NON_RETRYABLE,
            )
        repaired = _advance_if_needed(uow, record, stage)
        if repaired:
            uow.commit()
        return repaired
    except (RecordAlreadyExistsError, StaleRecordVersionError):
        return False
    except RepositoryUnavailableError as error:
        raise _persistence_error(error, stage) from error
    finally:
        uow.rollback()


def _advance_if_needed(uow: UnitOfWork, record: VersionedCallRecord, stage: PipelineStage) -> bool:
    target = {
        PipelineStage.TRANSCRIPTION: CallProcessingStatus.TRANSCRIBED,
        PipelineStage.DIARIZATION: CallProcessingStatus.DIARIZED,
        PipelineStage.ALIGNMENT: None,
        PipelineStage.ROLE_ASSIGNMENT: CallProcessingStatus.ROLES_ASSIGNED,
        PipelineStage.EVALUATION: CallProcessingStatus.EVALUATED,
        PipelineStage.AGGREGATION: None,
    }[stage]
    if target is None or record.value.status in _compatible_statuses(stage):
        return False
    path = _status_path(record.value.status, target)
    if path is None:
        raise PipelinePrerequisiteError(
            "call status cannot be repaired toward artifact checkpoint",
            stage=stage,
            reason_code=PipelineFailureReason.STATUS_ARTIFACT_INCONSISTENCY,
            retry_classification=PipelineRetryClassification.NON_RETRYABLE,
        )
    call = record.value
    for hop in path:
        call = call.advance_to(hop)
    uow.calls.update(call, expected_revision=record.revision)
    return True


def _status_path(
    current: CallProcessingStatus,
    target: CallProcessingStatus,
) -> tuple[CallProcessingStatus, ...] | None:
    order = (
        CallProcessingStatus.VALIDATED,
        CallProcessingStatus.TRANSCRIBED,
        CallProcessingStatus.DIARIZED,
        CallProcessingStatus.ROLES_ASSIGNED,
        CallProcessingStatus.EVALUATED,
    )
    if current not in order or target not in order:
        return None
    current_idx = order.index(current)
    target_idx = order.index(target)
    if target_idx <= current_idx:
        return None
    return order[current_idx + 1 : target_idx + 1]


def _complete_chain(uow: UnitOfWork, call_id: str, stage: PipelineStage) -> bool:
    p = uow.processing_results
    if p.find_transcription(call_id) is None:
        return False
    if stage is PipelineStage.TRANSCRIPTION:
        return True
    if p.find_diarization(call_id) is None:
        return False
    if stage in {PipelineStage.DIARIZATION, PipelineStage.ALIGNMENT}:
        return True
    if p.find_alignment(call_id) is None or p.find_role_assignment(call_id) is None:
        return False
    if stage is PipelineStage.ROLE_ASSIGNMENT:
        return True
    # EVALUATION / AGGREGATION status repair requires evaluation elsewhere.
    return stage in {PipelineStage.EVALUATION, PipelineStage.AGGREGATION}


def _expected_evaluation_key(
    request: RunCallPipelineRequest, deps: PipelineDependencies
) -> EvaluationKey:
    assert request.rubric_id is not None and request.rubric_version is not None
    try:
        return EvaluationKey(
            call_id=request.call_id,
            rubric_id=request.rubric_id,
            rubric_version=request.rubric_version,
            provider_name=deps.evaluation_provider.provider_name,
            model_name=deps.evaluation_provider.model_name,
        )
    except Exception as error:
        from sales_call_agent.persistence.exceptions import InvalidPersistenceInputError

        if isinstance(error, InvalidPersistenceInputError):
            raise InvalidPipelineRequestError(
                "evaluation provider identity is invalid",
                stage=PipelineStage.EVALUATION,
                reason_code=PipelineFailureReason.INVALID_REQUEST,
                retry_classification=PipelineRetryClassification.NON_RETRYABLE,
            ) from error
        raise


def _find_evaluation_by_key(
    deps: PipelineDependencies, key: EvaluationKey
) -> CallEvaluationResult | None:
    uow = deps.unit_of_work_factory()
    try:
        return uow.evaluations.find(key)
    finally:
        uow.rollback()


def _result_exists(
    call_id: str,
    stage: PipelineStage,
    deps: PipelineDependencies,
    evaluation_key: EvaluationKey | None,
) -> bool:
    uow = deps.unit_of_work_factory()
    try:
        if stage is PipelineStage.TRANSCRIPTION:
            return uow.processing_results.find_transcription(call_id) is not None
        if stage is PipelineStage.DIARIZATION:
            return uow.processing_results.find_diarization(call_id) is not None
        if stage is PipelineStage.ALIGNMENT:
            return uow.processing_results.find_alignment(call_id) is not None
        if stage is PipelineStage.ROLE_ASSIGNMENT:
            return uow.processing_results.find_role_assignment(call_id) is not None
        if stage is PipelineStage.EVALUATION:
            return evaluation_key is not None and uow.evaluations.find(evaluation_key) is not None
        return (
            evaluation_key is not None
            and uow.call_scores.find(
                CallScoreKey(
                    evaluation_key=evaluation_key,
                    aggregation_policy_fingerprint=aggregation_policy_fingerprint(
                        deps.aggregation_config
                    ),
                )
            )
            is not None
        )
    finally:
        uow.rollback()


def _persist_failure_status(call_id: str, stage: PipelineStage, deps: PipelineDependencies) -> None:
    if stage is PipelineStage.AGGREGATION:
        return
    uow = deps.unit_of_work_factory()
    try:
        record = uow.calls.get(call_id)
        # Do not fail if this stage already completed concurrently.
        if _result_exists(call_id, stage, deps, evaluation_key=None):
            return
        if record.value.status in _compatible_statuses(stage):
            return
        if not record.value.status.can_transition_to(CallProcessingStatus.FAILED):
            return
        uow.calls.update(
            record.value.advance_to(CallProcessingStatus.FAILED),
            expected_revision=record.revision,
        )
        uow.commit()
    except (
        RepositoryUnavailableError,
        RecordAlreadyExistsError,
        StaleRecordVersionError,
        RecordNotFoundError,
    ):
        return
    finally:
        uow.rollback()


def _provider_call(stage: PipelineStage, operation: object) -> object:
    try:
        return operation()  # type: ignore[operator]
    except (
        TranscriptionProviderUnavailableError,
        DiarizationProviderUnavailableError,
        EvaluationProviderUnavailableError,
        RepositoryUnavailableError,
    ) as error:
        reason = (
            PipelineFailureReason.REPOSITORY_UNAVAILABLE
            if isinstance(error, RepositoryUnavailableError)
            else PipelineFailureReason.PROVIDER_UNAVAILABLE
        )
        raise PipelineStageExecutionError(
            "stage provider is temporarily unavailable",
            stage=stage,
            reason_code=reason,
            retry_classification=PipelineRetryClassification.RETRYABLE,
        ) from error
    except (
        TranscriptionTimeoutError,
        DiarizationTimeoutError,
        EvaluationTimeoutError,
    ) as error:
        raise PipelineStageExecutionError(
            "stage provider timed out",
            stage=stage,
            reason_code=PipelineFailureReason.PROVIDER_TIMEOUT,
            retry_classification=PipelineRetryClassification.RETRYABLE,
        ) from error
    except (
        TranscriptionRequestFailedError,
        DiarizationRequestFailedError,
        EvaluationRequestFailedError,
    ) as error:
        raise PipelineStageExecutionError(
            "stage provider request failed",
            stage=stage,
            reason_code=PipelineFailureReason.PROVIDER_REQUEST_FAILED,
            retry_classification=PipelineRetryClassification.NON_RETRYABLE,
        ) from error
    except PipelineOrchestrationError:
        raise
    except DomainError as error:
        raise PipelineStageExecutionError(
            "stage returned invalid data",
            stage=stage,
            reason_code=PipelineFailureReason.INVALID_PROVIDER_OUTPUT,
            retry_classification=PipelineRetryClassification.NON_RETRYABLE,
        ) from error


def _required_audio(
    request: RunCallPipelineRequest, stage: PipelineStage
) -> NormalizedAudioReference:
    if request.normalized_audio is None:
        raise PipelinePrerequisiteError(
            "normalized audio is required",
            stage=stage,
            reason_code=PipelineFailureReason.MISSING_NORMALIZED_AUDIO,
            retry_classification=PipelineRetryClassification.NON_RETRYABLE,
        )
    return request.normalized_audio


def _validate_score(
    score: CallScoreResult,
    rubric: SalesRubric,
    evaluation: CallEvaluationResult,
    deps: PipelineDependencies,
) -> None:
    expected = tuple(item.criterion_id for item in rubric.criteria)
    actual = tuple(item.criterion_id for item in score.criterion_contributions)
    fingerprint = aggregation_policy_fingerprint(score.config)
    expected_fp = aggregation_policy_fingerprint(deps.aggregation_config)
    if (
        score.call_id != evaluation.call_id
        or score.rubric_id != rubric.rubric_id
        or score.rubric_version != rubric.version
        or score.config != deps.aggregation_config
        or fingerprint != expected_fp
        or actual != expected
    ):
        raise PipelinePrerequisiteError(
            "persisted score is malformed",
            stage=PipelineStage.AGGREGATION,
            reason_code=PipelineFailureReason.MALFORMED_PERSISTED_DATA,
            retry_classification=PipelineRetryClassification.NON_RETRYABLE,
        )


def _compatible_statuses(stage: PipelineStage) -> frozenset[CallProcessingStatus]:
    return {
        PipelineStage.TRANSCRIPTION: TRANSCRIPTION_COMPATIBLE,
        PipelineStage.DIARIZATION: DIARIZATION_COMPATIBLE,
        PipelineStage.ALIGNMENT: DIARIZATION_COMPATIBLE,
        PipelineStage.ROLE_ASSIGNMENT: ROLE_COMPATIBLE,
        PipelineStage.EVALUATION: EVALUATION_COMPATIBLE,
        PipelineStage.AGGREGATION: EVALUATION_COMPATIBLE,
    }[stage]


def _warning_codes_from_outcomes(
    outcomes: list[PipelineStageOutcome],
) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for outcome in outcomes:
        for code in outcome.warning_codes:
            if code not in seen:
                seen.add(code)
                ordered.append(code)
    return tuple(ordered)


def _add_target_quality_flags(
    flags: set[PipelineRunQualityFlag],
    target: PipelineTarget,
    artifacts: _Artifacts,
) -> None:
    from sales_call_agent.aggregation.models import CallScorePublicationStatus

    if (
        target is PipelineTarget.EVALUATION
        and artifacts.evaluation is not None
        and artifacts.evaluation.human_review_count > 0
    ):
        flags.add(PipelineRunQualityFlag.HUMAN_REVIEW_REQUIRED)
    if target is PipelineTarget.AGGREGATION and artifacts.score is not None:
        score = artifacts.score
        if score.human_review_count > 0 or (
            score.publication_status is CallScorePublicationStatus.HUMAN_REVIEW_REQUIRED
        ):
            flags.add(PipelineRunQualityFlag.HUMAN_REVIEW_REQUIRED)
        if score.publication_status is CallScorePublicationStatus.LIMITED_COVERAGE:
            flags.add(PipelineRunQualityFlag.LIMITED_COVERAGE)
        if score.publication_status is CallScorePublicationStatus.NO_SCORABLE_CRITERIA:
            flags.add(PipelineRunQualityFlag.NO_SCORABLE_CRITERIA)


def _missing(stage: PipelineStage) -> PipelinePrerequisiteError:
    return PipelinePrerequisiteError(
        "required pipeline artifact is missing",
        stage=stage,
        reason_code=PipelineFailureReason.MISSING_PREREQUISITE,
        retry_classification=PipelineRetryClassification.NON_RETRYABLE,
    )


def _invalid_request(message: str) -> InvalidPipelineRequestError:
    return InvalidPipelineRequestError(
        message,
        reason_code=PipelineFailureReason.INVALID_REQUEST,
        retry_classification=PipelineRetryClassification.NON_RETRYABLE,
    )


def _persistence_error(
    error: RepositoryUnavailableError, stage: PipelineStage
) -> PipelineStagePersistenceError:
    return PipelineStagePersistenceError(
        "repository is unavailable",
        stage=stage,
        reason_code=PipelineFailureReason.REPOSITORY_UNAVAILABLE,
        retry_classification=PipelineRetryClassification.RETRYABLE,
    )
