"""Fixtures and observable provider adapters for orchestration tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
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
from sales_call_agent.orchestration.models import NormalizedAudioReference
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.speaker_identity.models import (
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider


@dataclass
class CountingTranscriptionProvider:
    delegate: Any
    calls: int = 0
    received_paths: list[str] | None = None
    events: list[str] | None = None

    @property
    def provider_name(self) -> str:
        return self.delegate.provider_name

    @property
    def model_name(self) -> str:
        return self.delegate.model_name

    def transcribe(self, request: Any) -> Any:
        self.calls += 1
        if self.received_paths is not None:
            self.received_paths.append(request.normalized_audio_path)
        if self.events is not None:
            self.events.append("transcribe")
        return self.delegate.transcribe(request)


@dataclass
class CountingDiarizationProvider:
    delegate: Any
    calls: int = 0
    received_paths: list[str] | None = None
    events: list[str] | None = None

    @property
    def provider_name(self) -> str:
        return self.delegate.provider_name

    @property
    def model_name(self) -> str:
        return self.delegate.model_name

    def diarize(self, request: Any) -> Any:
        self.calls += 1
        if self.received_paths is not None:
            self.received_paths.append(request.normalized_audio_path)
        if self.events is not None:
            self.events.append("diarize")
        return self.delegate.diarize(request)


@dataclass
class CountingEvaluationProvider:
    delegate: Any
    calls: int = 0
    events: list[str] | None = None

    @property
    def provider_name(self) -> str:
        return self.delegate.provider_name

    @property
    def model_name(self) -> str:
        return self.delegate.model_name

    def evaluate(self, request: Any) -> Any:
        self.calls += 1
        if self.events is not None:
            self.events.append("evaluate")
        return self.delegate.evaluate(request)


@pytest.fixture
def call() -> Call:
    original_path = r"C:\SECRET_ORIGINAL_AUDIO\SECRET_CALL.mp3"
    return Call(
        metadata=CallMetadata(
            call_id="call-orchestration-001",
            seller_number="SECRET_SELLER",
            source_type=SourceType.RECORDER_APP,
            call_timestamp=datetime(2026, 7, 29, tzinfo=UTC),
            duration_seconds=4.0,
            counterparty_phone="SECRET_CUSTOMER",
            original_filename="SECRET_CALL.mp3",
            audio_channels=AudioChannels.MONO,
            storage_path=original_path,
        ),
        audio=AudioAsset(
            storage_path=original_path,
            audio_channels=AudioChannels.MONO,
            content_hash="original-secret-hash",
        ),
        status=CallProcessingStatus.VALIDATED,
    )


@pytest.fixture
def normalized_audio() -> NormalizedAudioReference:
    return NormalizedAudioReference(
        storage_path=Path("normalized/SECRET_SHOULD_NOT_LEAK.asr.wav"),
        content_hash="normalized-hash-001",
        duration_seconds=4.0,
    )


@pytest.fixture
def approved_rubric() -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale-orchestration-001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="not observed"),
            RubricScoreLevel(score=1.0, label="yes", description="observed"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric-orchestration-001",
        name="Synthetic rubric",
        version="1.0.0",
        description="Synthetic rubric for orchestration tests.",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion-orchestration-001",
                name="Discovery",
                definition="Asked a discovery question.",
                positive_guidance="Ask a question.",
                negative_guidance="Do not immediately pitch.",
                category=RubricCriterionCategory.DISCOVERY,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(),
            ),
        ),
    )


@pytest.fixture
def role_evidence() -> tuple[RoleEvidence, ...]:
    return (
        RoleEvidence(
            evidence_id="evidence-seller-001",
            speaker_label="SPEAKER_00",
            evidence_type=RoleEvidenceType.VOICE_IDENTITY_MATCH,
            suggested_role=SpeakerRole.SELLER,
        ),
        RoleEvidence(
            evidence_id="evidence-customer-001",
            speaker_label="SPEAKER_01",
            evidence_type=RoleEvidenceType.KNOWN_SELLER_SOURCE,
            suggested_role=SpeakerRole.CUSTOMER,
        ),
    )


@pytest.fixture
def store() -> InMemoryPersistenceStore:
    return InMemoryPersistenceStore()


@pytest.fixture
def counting_transcription_provider() -> CountingTranscriptionProvider:
    return CountingTranscriptionProvider(DeterministicFakeTranscriptionProvider())


@pytest.fixture
def counting_diarization_provider() -> CountingDiarizationProvider:
    return CountingDiarizationProvider(DeterministicFakeDiarizationProvider())


@pytest.fixture
def counting_evaluation_provider() -> CountingEvaluationProvider:
    return CountingEvaluationProvider(DeterministicFakeEvaluationProvider())


@pytest.fixture
def dependencies(
    store: InMemoryPersistenceStore,
    counting_transcription_provider: CountingTranscriptionProvider,
    counting_diarization_provider: CountingDiarizationProvider,
    counting_evaluation_provider: CountingEvaluationProvider,
) -> PipelineDependencies:
    return PipelineDependencies(
        transcription_provider=counting_transcription_provider,
        diarization_provider=counting_diarization_provider,
        evaluation_provider=counting_evaluation_provider,
        unit_of_work_factory=InMemoryUnitOfWorkFactory(store=store),
    )


@pytest.fixture
def seed_call_and_approved_rubric(
    store: InMemoryPersistenceStore, call: Call, approved_rubric: SalesRubric
) -> Any:
    def seed(*, call_value: Call = call, rubric: SalesRubric = approved_rubric) -> None:
        factory = InMemoryUnitOfWorkFactory(store=store)
        uow = factory()
        uow.calls.add(call_value)
        draft = replace(rubric, status=RubricStatus.DRAFT)
        uow.rubrics.add(draft)
        uow.rubrics.update_status(
            rubric.rubric_id,
            rubric.version,
            status=RubricStatus.APPROVED,
            expected_revision=1,
        )
        uow.commit()

    return seed
