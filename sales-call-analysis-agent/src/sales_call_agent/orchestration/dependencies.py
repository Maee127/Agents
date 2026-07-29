"""Dependency container and unit-of-work factory for pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sales_call_agent.aggregation.models import AggregationConfig
from sales_call_agent.alignment.models import AlignmentConfig
from sales_call_agent.diarization.provider import DiarizationProvider
from sales_call_agent.evaluation.provider import EvaluationProvider
from sales_call_agent.persistence.fake import InMemoryPersistenceStore, InMemoryUnitOfWork
from sales_call_agent.persistence.unit_of_work import UnitOfWork
from sales_call_agent.speaker_identity.models import RoleAssignmentConfig
from sales_call_agent.transcription.provider import TranscriptionProvider


class UnitOfWorkFactory(Protocol):
    """Provider-independent factory that creates an isolated unit of work."""

    def __call__(self) -> UnitOfWork: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class InMemoryUnitOfWorkFactory:
    """Frozen callable factory over a shared in-memory persistence store."""

    store: InMemoryPersistenceStore = field(repr=False)

    def __call__(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store=self.store)


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineDependencies:
    """Frozen dependency container for one orchestration attempt.

    All providers are constructor-required for wiring simplicity. That does not
    mean every provider is invoked for every target: persisted canonical results
    are reused without calling the corresponding provider.
    """

    transcription_provider: TranscriptionProvider = field(repr=False)
    diarization_provider: DiarizationProvider = field(repr=False)
    evaluation_provider: EvaluationProvider = field(repr=False)
    unit_of_work_factory: UnitOfWorkFactory = field(repr=False)
    alignment_config: AlignmentConfig = field(default_factory=AlignmentConfig)
    role_assignment_config: RoleAssignmentConfig = field(default_factory=RoleAssignmentConfig)
    aggregation_config: AggregationConfig = field(default_factory=AggregationConfig)
    transcription_expected_language: str | None = None
    transcription_provider_config_id: str | None = None
    diarization_provider_config_id: str | None = None
    evaluation_provider_config_id: str | None = None
