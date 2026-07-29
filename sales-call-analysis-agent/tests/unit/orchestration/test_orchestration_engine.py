"""Checkpoint, retry, and privacy tests for ``run_call_pipeline``."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from sales_call_agent.diarization.fake import (
    DeterministicFakeDiarizationProvider,
    FakeDiarizationFailureMode,
)
from sales_call_agent.domain.models import Call, CallProcessingStatus
from sales_call_agent.orchestration.dependencies import (
    InMemoryUnitOfWorkFactory,
    PipelineDependencies,
)
from sales_call_agent.orchestration.engine import _repair_status, run_call_pipeline
from sales_call_agent.orchestration.exceptions import (
    InvalidPipelineRequestError,
    PipelinePrerequisiteError,
    PipelineStageExecutionError,
)
from sales_call_agent.orchestration.models import (
    PipelineFailureReason,
    PipelineStage,
    PipelineStageOutcomeStatus,
    PipelineTarget,
    RunCallPipelineRequest,
)
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentQualityFlag,
    RoleAssignmentResult,
    RoleAssignmentStatus,
    RoleDecisionReason,
    SpeakerRole,
    SpeakerRoleAssignment,
)


def _request(
    call_id: str,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    target: PipelineTarget = PipelineTarget.AGGREGATION,
) -> RunCallPipelineRequest:
    kwargs: dict[str, Any] = {
        "call_id": call_id,
        "target": target,
        "normalized_audio": normalized_audio,
        # The deterministic ASR output occupies only SPEAKER_00's turn.  Keep
        # the full fixture for contract coverage, but pass aligned evidence.
        "role_evidence": role_evidence[:1],
    }
    if target is not PipelineTarget.ROLE_ASSIGNMENT:
        kwargs.update(rubric_id="rubric-orchestration-001", rubric_version="1.0.0")
    return RunCallPipelineRequest(**kwargs)


def _record(store: InMemoryPersistenceStore, call_id: str) -> Any:
    uow = InMemoryUnitOfWorkFactory(store=store)()
    try:
        return uow.calls.get(call_id)
    finally:
        uow.rollback()


def test_full_fresh_run_to_aggregation(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    result = run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence), dependencies
    )
    assert result.reached_stage is PipelineStage.AGGREGATION
    assert all(item.status is PipelineStageOutcomeStatus.EXECUTED for item in result.stage_outcomes)
    assert result.evaluation_key is not None
    assert result.call_score_key is not None
    assert (
        _record(dependencies.unit_of_work_factory.store, call.call_id).value.status
        is CallProcessingStatus.EVALUATED
    )


def test_role_assignment_target_stops_before_evaluation(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
    counting_evaluation_provider: Any,
) -> None:
    seed_call_and_approved_rubric()
    result = run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence, PipelineTarget.ROLE_ASSIGNMENT),
        dependencies,
    )
    assert result.evaluation_key is None
    assert len(result.stage_outcomes) == 4
    assert counting_evaluation_provider.calls == 0


def test_evaluation_target_stops_before_aggregation(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    result = run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence, PipelineTarget.EVALUATION),
        dependencies,
    )
    assert result.reached_stage is PipelineStage.EVALUATION
    assert result.evaluation_key is not None
    assert result.call_score_key is None


def test_unapproved_rubric_is_rejected(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    approved_rubric: Any,
) -> None:
    uow = dependencies.unit_of_work_factory()
    uow.calls.add(call)
    uow.rubrics.add(replace(approved_rubric, status=approved_rubric.status.DRAFT))
    uow.commit()
    with pytest.raises(PipelinePrerequisiteError) as raised:
        run_call_pipeline(_request(call.call_id, normalized_audio, role_evidence), dependencies)
    assert raised.value.reason_code is PipelineFailureReason.RUBRIC_NOT_APPROVED


def test_missing_call_is_rejected(
    normalized_audio: Any, role_evidence: tuple[Any, ...], dependencies: PipelineDependencies
) -> None:
    with pytest.raises(PipelinePrerequisiteError) as raised:
        run_call_pipeline(
            _request("missing-call-001", normalized_audio, role_evidence), dependencies
        )
    assert raised.value.reason_code is PipelineFailureReason.MISSING_CALL


def test_missing_normalized_audio_is_rejected_when_transcription_missing(
    call: Call,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    with pytest.raises(PipelinePrerequisiteError) as raised:
        run_call_pipeline(_request(call.call_id, None, role_evidence), dependencies)
    assert raised.value.reason_code is PipelineFailureReason.MISSING_NORMALIZED_AUDIO


def test_normalized_audio_is_optional_when_all_required_artifacts_exist(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence, PipelineTarget.ROLE_ASSIGNMENT),
        dependencies,
    )
    result = run_call_pipeline(
        _request(call.call_id, None, (), PipelineTarget.ROLE_ASSIGNMENT), dependencies
    )
    assert all(item.status is PipelineStageOutcomeStatus.REUSED for item in result.stage_outcomes)


def test_call_original_audio_is_never_sent_to_providers(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
    counting_transcription_provider: Any,
    counting_diarization_provider: Any,
) -> None:
    seed_call_and_approved_rubric()
    paths: list[str] = []
    counting_transcription_provider.received_paths = paths
    counting_diarization_provider.received_paths = paths
    run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence, PipelineTarget.ROLE_ASSIGNMENT),
        dependencies,
    )
    assert paths == [str(normalized_audio.storage_path), str(normalized_audio.storage_path)]
    assert call.audio.storage_path not in paths


def test_second_run_reuses_everything_without_provider_calls_or_revision_change(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
    counting_transcription_provider: Any,
    counting_diarization_provider: Any,
    counting_evaluation_provider: Any,
) -> None:
    seed_call_and_approved_rubric()
    first = run_call_pipeline(_request(call.call_id, normalized_audio, role_evidence), dependencies)
    before = _record(dependencies.unit_of_work_factory.store, call.call_id).revision
    second = run_call_pipeline(_request(call.call_id, None, ()), dependencies)
    after = _record(dependencies.unit_of_work_factory.store, call.call_id).revision
    assert first.stage_outcomes != second.stage_outcomes
    assert all(item.status is PipelineStageOutcomeStatus.REUSED for item in second.stage_outcomes)
    assert (
        counting_transcription_provider.calls,
        counting_diarization_provider.calls,
        counting_evaluation_provider.calls,
    ) == (1, 1, 1)
    assert before == after


def test_third_run_has_same_reused_outcomes_as_second(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    first = run_call_pipeline(_request(call.call_id, normalized_audio, role_evidence), dependencies)
    second = run_call_pipeline(_request(call.call_id, None, ()), dependencies)
    third = run_call_pipeline(_request(call.call_id, None, ()), dependencies)
    assert first.stage_outcomes != second.stage_outcomes
    assert third.stage_outcomes == second.stage_outcomes


def test_retryable_diarization_failure_leaves_transcribed_and_rerun_resumes(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    failing = DeterministicFakeDiarizationProvider(
        failure_modes_by_call_id={call.call_id: FakeDiarizationFailureMode.PROVIDER_UNAVAILABLE}
    )
    failing_dependencies = replace(dependencies, diarization_provider=failing)
    with pytest.raises(PipelineStageExecutionError) as raised:
        run_call_pipeline(
            _request(call.call_id, normalized_audio, role_evidence), failing_dependencies
        )
    assert raised.value.stage is PipelineStage.DIARIZATION
    assert (
        _record(dependencies.unit_of_work_factory.store, call.call_id).value.status
        is CallProcessingStatus.TRANSCRIBED
    )
    result = run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence), dependencies
    )
    assert result.stage_outcomes[0].status is PipelineStageOutcomeStatus.REUSED
    assert result.reached_stage is PipelineStage.AGGREGATION


def test_invalid_diarization_response_can_mark_failed_and_terminal_failed_rejects(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    invalid = DeterministicFakeDiarizationProvider(
        failure_modes_by_call_id={call.call_id: FakeDiarizationFailureMode.INVALID_RESPONSE}
    )
    with pytest.raises(PipelineStageExecutionError) as raised:
        run_call_pipeline(
            _request(call.call_id, normalized_audio, role_evidence),
            replace(dependencies, diarization_provider=invalid),
        )
    assert raised.value.reason_code is PipelineFailureReason.INVALID_PROVIDER_OUTPUT
    assert (
        _record(dependencies.unit_of_work_factory.store, call.call_id).value.status
        is CallProcessingStatus.FAILED
    )
    with pytest.raises(InvalidPipelineRequestError):
        run_call_pipeline(_request(call.call_id, normalized_audio, role_evidence), dependencies)


def test_role_evidence_is_ignored_when_roles_are_reused(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    run_call_pipeline(
        _request(call.call_id, normalized_audio, role_evidence, PipelineTarget.ROLE_ASSIGNMENT),
        dependencies,
    )
    result = run_call_pipeline(
        _request(call.call_id, None, (), PipelineTarget.ROLE_ASSIGNMENT), dependencies
    )
    assert result.stage_outcomes[-1].status is PipelineStageOutcomeStatus.REUSED


def test_empty_evidence_is_supported_when_roles_are_executed(
    call: Call,
    normalized_audio: Any,
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    result = run_call_pipeline(_request(call.call_id, normalized_audio, ()), dependencies)
    assert result.reached_stage is PipelineStage.AGGREGATION


def test_status_repair_requires_complete_artifact_chain(
    call: Call,
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
) -> None:
    seed_call_and_approved_rubric()
    role_result = RoleAssignmentResult(
        call_id=call.call_id,
        assignments=(
            SpeakerRoleAssignment(
                speaker_label="SPEAKER_00",
                role=SpeakerRole.SELLER,
                status=RoleAssignmentStatus.ASSIGNED,
                reason_code=RoleDecisionReason.STRONG_EVIDENCE,
                supporting_evidence_ids=("evidence-001",),
            ),
            SpeakerRoleAssignment(
                speaker_label="SPEAKER_01",
                role=SpeakerRole.CUSTOMER,
                status=RoleAssignmentStatus.ASSIGNED,
                reason_code=RoleDecisionReason.STRONG_EVIDENCE,
                supporting_evidence_ids=("evidence-002",),
            ),
        ),
        quality_flags=(RoleAssignmentQualityFlag.MULTI_PARTY_CALL,),
    )
    uow = dependencies.unit_of_work_factory()
    uow.processing_results.add_role_assignment(role_result)
    uow.commit()
    with pytest.raises(PipelinePrerequisiteError) as raised:
        _repair_status(call.call_id, PipelineStage.ROLE_ASSIGNMENT, dependencies)
    assert raised.value.reason_code is PipelineFailureReason.STATUS_ARTIFACT_INCONSISTENCY


@dataclass
class _LoggingUnitOfWork:
    delegate: Any
    events: list[str]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def commit(self) -> None:
        self.events.append("commit")
        self.delegate.commit()

    def rollback(self) -> None:
        self.delegate.rollback()


@dataclass
class _LoggingFactory:
    store: InMemoryPersistenceStore
    events: list[str]

    def __call__(self) -> _LoggingUnitOfWork:
        self.events.append("uow_create")
        return _LoggingUnitOfWork(InMemoryUnitOfWorkFactory(store=self.store)(), self.events)


def test_provider_calls_happen_after_uow_is_released(
    call: Call,
    normalized_audio: Any,
    role_evidence: tuple[Any, ...],
    dependencies: PipelineDependencies,
    seed_call_and_approved_rubric: Any,
    counting_transcription_provider: Any,
    counting_diarization_provider: Any,
    counting_evaluation_provider: Any,
) -> None:
    seed_call_and_approved_rubric()
    events: list[str] = []
    counting_transcription_provider.events = events
    counting_diarization_provider.events = events
    counting_evaluation_provider.events = events
    logged = replace(
        dependencies,
        unit_of_work_factory=_LoggingFactory(dependencies.unit_of_work_factory.store, events),
    )
    run_call_pipeline(_request(call.call_id, normalized_audio, role_evidence), logged)
    assert events.index("transcribe") > events.index("uow_create")
    assert events.index("diarize") > events.index("transcribe")
    assert events.index("evaluate") > events.index("diarize")
    assert events.count("commit") >= 4
