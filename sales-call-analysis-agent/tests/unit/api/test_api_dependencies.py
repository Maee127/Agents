"""Unit tests for ApiDependencies isolation and repr privacy."""

from __future__ import annotations

from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.evaluation.fake import DeterministicFakeEvaluationProvider
from sales_call_agent.orchestration.dependencies import (
    InMemoryUnitOfWorkFactory,
    PipelineDependencies,
)
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider


def _make_deps() -> ApiDependencies:
    store = InMemoryPersistenceStore()
    uow_factory = InMemoryUnitOfWorkFactory(store=store)
    pipeline_deps = PipelineDependencies(
        transcription_provider=DeterministicFakeTranscriptionProvider(),
        diarization_provider=DeterministicFakeDiarizationProvider(),
        evaluation_provider=DeterministicFakeEvaluationProvider(),
        unit_of_work_factory=uow_factory,
    )
    return ApiDependencies(
        unit_of_work_factory=uow_factory,
        pipeline_dependencies=pipeline_deps,
    )


def test_api_dependencies_repr_hides_providers() -> None:
    deps = _make_deps()
    r = repr(deps)
    assert "unit_of_work_factory" not in r
    assert "pipeline_dependencies" not in r


def test_two_api_dependency_instances_are_independent() -> None:
    deps_a = _make_deps()
    deps_b = _make_deps()
    assert deps_a is not deps_b
    assert deps_a.unit_of_work_factory is not deps_b.unit_of_work_factory


def test_api_dependencies_is_frozen() -> None:
    deps = _make_deps()
    try:
        deps.unit_of_work_factory = deps.unit_of_work_factory  # type: ignore[misc]
        raise AssertionError("expected FrozenInstanceError")
    except Exception as exc:
        assert "frozen" in type(exc).__name__.lower() or "cannot" in str(exc).lower()
