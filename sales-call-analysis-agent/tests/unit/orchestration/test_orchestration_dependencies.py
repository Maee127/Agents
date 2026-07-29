"""Tests for dependency wiring contracts."""

from __future__ import annotations

import typing

from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.evaluation.fake import DeterministicFakeEvaluationProvider
from sales_call_agent.orchestration.dependencies import (
    InMemoryUnitOfWorkFactory,
    PipelineDependencies,
    UnitOfWorkFactory,
)
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider


def test_pipeline_dependencies_hides_provider_representations() -> None:
    dependencies = PipelineDependencies(
        transcription_provider=DeterministicFakeTranscriptionProvider(provider_name="SECRET_ASR"),
        diarization_provider=DeterministicFakeDiarizationProvider(provider_name="SECRET_DIAR"),
        evaluation_provider=DeterministicFakeEvaluationProvider(provider_name="SECRET_EVAL"),
        unit_of_work_factory=InMemoryUnitOfWorkFactory(store=InMemoryPersistenceStore()),
    )
    rendered = repr(dependencies)
    assert "SECRET_ASR" not in rendered
    assert "SECRET_DIAR" not in rendered
    assert "SECRET_EVAL" not in rendered


def test_in_memory_factory_is_structurally_assignable_to_protocol() -> None:
    factory: UnitOfWorkFactory = InMemoryUnitOfWorkFactory(store=InMemoryPersistenceStore())
    assert factory() is not None


def test_unit_of_work_factory_is_not_runtime_checkable() -> None:
    assert not getattr(UnitOfWorkFactory, "_is_runtime_protocol", False)
    assert not hasattr(typing, "is_protocol") or typing.is_protocol(UnitOfWorkFactory)
