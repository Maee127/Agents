"""Persisted end-to-end orchestration checks using deterministic providers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sales_call_agent.diarization.fake import (
    DeterministicFakeDiarizationProvider,
    FakeDiarizationFailureMode,
)
from sales_call_agent.domain.models import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    SourceType,
)
from sales_call_agent.evaluation.fake import DeterministicFakeEvaluationProvider
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    RubricCriterion,
    RubricCriterionCategory,
    RubricScoreLevel,
    RubricScoringScale,
    RubricStatus,
    SalesRubric,
)
from sales_call_agent.orchestration.dependencies import (
    InMemoryUnitOfWorkFactory,
    PipelineDependencies,
)
from sales_call_agent.orchestration.engine import run_call_pipeline
from sales_call_agent.orchestration.exceptions import PipelineStageExecutionError
from sales_call_agent.orchestration.models import (
    NormalizedAudioReference,
    PipelineStageOutcomeStatus,
    RunCallPipelineRequest,
)
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.speaker_identity.models import (
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider


def _call(call_id: str) -> Call:
    path = "original/SECRET_CALL.wav"
    return Call(
        metadata=CallMetadata(
            call_id=call_id,
            seller_number="SECRET_SELLER",
            source_type=SourceType.RECORDER_APP,
            call_timestamp=datetime(2026, 7, 29, tzinfo=UTC),
            duration_seconds=4.0,
            counterparty_phone="SECRET_CUSTOMER",
            original_filename="SECRET_CALL.wav",
            audio_channels=AudioChannels.MONO,
            storage_path=path,
        ),
        audio=AudioAsset(
            storage_path=path, audio_channels=AudioChannels.MONO, content_hash="original"
        ),
        status=CallProcessingStatus.VALIDATED,
    )


def _rubric() -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale-integration-001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="no"),
            RubricScoreLevel(score=1.0, label="yes", description="yes"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric-integration-001",
        name="Synthetic integration rubric",
        version="1.0.0",
        description="Synthetic only.",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion-integration-001",
                name="Discovery",
                definition="Question asked.",
                positive_guidance="Ask.",
                negative_guidance="Do not pitch.",
                category=RubricCriterionCategory.DISCOVERY,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(),
            ),
        ),
    )


def _seed(store: InMemoryPersistenceStore, call: Call, rubric: SalesRubric) -> None:
    uow = InMemoryUnitOfWorkFactory(store=store)()
    uow.calls.add(call)
    uow.rubrics.add(replace(rubric, status=RubricStatus.DRAFT))
    uow.rubrics.update_status(
        rubric.rubric_id, rubric.version, status=RubricStatus.APPROVED, expected_revision=1
    )
    uow.commit()


def _request(call_id: str, audio: NormalizedAudioReference | None) -> RunCallPipelineRequest:
    return RunCallPipelineRequest(
        call_id=call_id,
        normalized_audio=audio,
        rubric_id="rubric-integration-001",
        rubric_version="1.0.0",
        role_evidence=(
            RoleEvidence(
                evidence_id="evidence-integration-seller",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.VOICE_IDENTITY_MATCH,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
    )


def _dependencies(store: InMemoryPersistenceStore) -> PipelineDependencies:
    return PipelineDependencies(
        transcription_provider=DeterministicFakeTranscriptionProvider(),
        diarization_provider=DeterministicFakeDiarizationProvider(),
        evaluation_provider=DeterministicFakeEvaluationProvider(),
        unit_of_work_factory=InMemoryUnitOfWorkFactory(store=store),
    )


def test_persisted_full_flow_reuses_second_and_third_runs() -> None:
    store = InMemoryPersistenceStore()
    call = _call("call-integration-001")
    _seed(store, call, _rubric())
    dependencies = _dependencies(store)
    audio = NormalizedAudioReference(
        storage_path=Path("normalized/integration.asr.wav"),
        content_hash="normalized",
        duration_seconds=4,
    )
    first = run_call_pipeline(_request(call.call_id, audio), dependencies)
    second = run_call_pipeline(_request(call.call_id, None), dependencies)
    third = run_call_pipeline(_request(call.call_id, None), dependencies)
    assert all(item.status is PipelineStageOutcomeStatus.EXECUTED for item in first.stage_outcomes)
    assert all(item.status is PipelineStageOutcomeStatus.REUSED for item in second.stage_outcomes)
    assert third.stage_outcomes == second.stage_outcomes


def test_persisted_flow_resumes_after_retryable_diarization_failure() -> None:
    store = InMemoryPersistenceStore()
    call = _call("call-integration-retry-001")
    _seed(store, call, _rubric())
    audio = NormalizedAudioReference(
        storage_path=Path("normalized/retry.asr.wav"),
        content_hash="normalized-retry",
        duration_seconds=4,
    )
    dependencies = _dependencies(store)
    failing = replace(
        dependencies,
        diarization_provider=DeterministicFakeDiarizationProvider(
            failure_modes_by_call_id={
                call.call_id: FakeDiarizationFailureMode.PROVIDER_UNAVAILABLE,
            }
        ),
    )
    with pytest.raises(PipelineStageExecutionError):
        run_call_pipeline(_request(call.call_id, audio), failing)
    resumed = run_call_pipeline(_request(call.call_id, audio), dependencies)
    assert resumed.stage_outcomes[0].status is PipelineStageOutcomeStatus.REUSED
