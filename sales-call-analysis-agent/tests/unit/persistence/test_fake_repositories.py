"""Behavioral tests for in-memory persistence repositories."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sales_call_agent.domain.models import CallProcessingStatus
from sales_call_agent.evaluation.models import CallEvaluationResult, EvaluationQualityFlag
from sales_call_agent.knowledge.models import KnowledgeSourceStatus, RubricStatus
from sales_call_agent.persistence.exceptions import (
    InvalidPersistenceInputError,
    PersistenceConflictError,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleRecordVersionError,
)
from sales_call_agent.persistence.fake import (
    FakeFailureConfig,
    FakeFailureOperation,
    InMemoryPersistenceStore,
    InMemoryUnitOfWork,
)
from sales_call_agent.persistence.keys import EvaluationKey


def test_call_repository_add_update_and_list(call: object) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    first = uow.calls.add(call)  # type: ignore[arg-type]
    second = uow.calls.add(call)  # type: ignore[arg-type]
    assert first == second
    updated_call = replace(call, status=CallProcessingStatus.VALIDATED)  # type: ignore[arg-type]
    updated = uow.calls.update(updated_call, expected_revision=1)
    assert updated.revision == 2
    assert uow.calls.list_calls()[0].value.status is CallProcessingStatus.VALIDATED
    with pytest.raises(StaleRecordVersionError):
        uow.calls.update(updated_call, expected_revision=1)


def test_processing_results_use_single_canonical_record_per_stage(
    call: object,
    transcription_result: object,
) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    uow.processing_results.add_transcription(transcription_result)  # type: ignore[arg-type]
    uow.processing_results.add_transcription(transcription_result)  # type: ignore[arg-type]
    different = replace(transcription_result, model_name="other_model")  # type: ignore[arg-type]
    with pytest.raises(RecordAlreadyExistsError):
        uow.processing_results.add_transcription(different)
    with pytest.raises(RecordNotFoundError):
        uow.processing_results.get_transcription("call-other")


def test_knowledge_source_lifecycle_and_sections_atomicity(
    knowledge_source: object,
    knowledge_sections: tuple[object, ...],
) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    record = uow.knowledge.add_source(knowledge_source)  # type: ignore[arg-type]
    assert record.revision == 1
    updated_source = replace(knowledge_source, status=KnowledgeSourceStatus.APPROVED)  # type: ignore[arg-type]
    updated = uow.knowledge.update_source(updated_source, expected_revision=1)
    assert updated.revision == 2
    same = uow.knowledge.update_source(updated_source, expected_revision=2)
    assert same.revision == 2
    with pytest.raises(StaleRecordVersionError):
        uow.knowledge.update_source(updated_source, expected_revision=1)

    uow.knowledge.add_sections("source_001", knowledge_sections)  # type: ignore[arg-type]
    assert len(uow.knowledge.get_sections("source_001")) == 2

    bad_section = replace(knowledge_sections[0], source_id="source_999")  # type: ignore[arg-type]
    with pytest.raises(InvalidPersistenceInputError):
        uow.knowledge.add_sections("source_001", (bad_section,))  # type: ignore[arg-type]
    assert len(uow.knowledge.get_sections("source_001")) == 2


def test_rubric_status_lifecycle_and_semver_latest(rubric: object) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    record = uow.rubrics.add(rubric)  # type: ignore[arg-type]
    promoted = uow.rubrics.update_status(
        record.value.rubric_id,
        record.value.version,
        status=RubricStatus.APPROVED,
        expected_revision=1,
    )
    assert promoted.revision == 2
    retired = uow.rubrics.update_status(
        promoted.value.rubric_id,
        promoted.value.version,
        status=RubricStatus.RETIRED,
        expected_revision=2,
    )
    assert retired.revision == 3
    with pytest.raises(RecordAlreadyExistsError):
        uow.rubrics.update_status(
            retired.value.rubric_id,
            retired.value.version,
            status=RubricStatus.APPROVED,
            expected_revision=3,
        )

    lower_approved = replace(rubric, version="1.9.0", status=RubricStatus.APPROVED)  # type: ignore[arg-type]
    higher_retired = replace(rubric, version="1.10.0", status=RubricStatus.RETIRED)  # type: ignore[arg-type]
    uow.rubrics.add(lower_approved)
    uow.rubrics.add(higher_retired)
    latest = uow.rubrics.get_latest_approved(record.value.rubric_id)
    assert latest.value.version == "1.9.0"


def test_evaluation_and_call_score_keys_and_conflicts(
    evaluation_result: CallEvaluationResult,
    call_score_result: object,
) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    key = uow.evaluations.add(evaluation_result)
    same = uow.evaluations.add(evaluation_result)
    assert key == same
    changed_eval = replace(
        evaluation_result,
        warning_codes=("WARN_A",),
        quality_flags=(
            EvaluationQualityFlag.ALL_CRITERIA_SCORED,
            EvaluationQualityFlag.PROVIDER_WARNING,
        ),
    )
    with pytest.raises(RecordAlreadyExistsError):
        uow.evaluations.add(changed_eval)

    score_key = uow.call_scores.add(call_score_result, evaluation_key=key)  # type: ignore[arg-type]
    assert uow.call_scores.get(score_key) == call_score_result  # type: ignore[comparison-overlap]
    with pytest.raises(InvalidPersistenceInputError):
        wrong = EvaluationKey(
            call_id="call-other",
            rubric_id=key.rubric_id,
            rubric_version=key.rubric_version,
            provider_name=key.provider_name,
            model_name=key.model_name,
        )
        uow.call_scores.add(call_score_result, evaluation_key=wrong)  # type: ignore[arg-type]


def test_ordering_rules(
    call: object,
    knowledge_source: object,
    rubric: object,
    evaluation_result: CallEvaluationResult,
) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    uow.calls.add(call)  # type: ignore[arg-type]
    uow.calls.add(replace(call, metadata=replace(call.metadata, call_id="call-zzz")))  # type: ignore[arg-type]
    assert tuple(item.value.call_id for item in uow.calls.list_calls()) == (
        "call-abc123def4567890",
        "call-zzz",
    )

    uow.knowledge.add_source(knowledge_source)  # type: ignore[arg-type]
    uow.knowledge.add_source(replace(knowledge_source, source_id="source_002"))  # type: ignore[arg-type]
    assert tuple(item.value.source_id for item in uow.knowledge.list_sources()) == (
        "source_001",
        "source_002",
    )

    uow.rubrics.add(rubric)  # type: ignore[arg-type]
    uow.rubrics.add(replace(rubric, version="1.10.0"))  # type: ignore[arg-type]
    uow.rubrics.add(replace(rubric, version="1.9.0"))  # type: ignore[arg-type]
    versions = uow.rubrics.list_versions(rubric.rubric_id)  # type: ignore[attr-defined]
    assert tuple(item.value.version for item in versions) == ("1.0.0", "1.9.0", "1.10.0")

    first_key = uow.evaluations.add(evaluation_result)
    second_eval = replace(evaluation_result, model_name="model_eval_v2")
    second_key = uow.evaluations.add(second_eval)
    listed = uow.evaluations.list_for_call(evaluation_result.call_id)
    assert listed == tuple(
        value
        for _key, value in sorted(
            ((first_key, evaluation_result), (second_key, second_eval)),
            key=lambda pair: pair[0].sort_key,
        )
    )


def test_privacy_repr_and_conflict_hierarchy(
    call: object,
    knowledge_source: object,
    rubric: object,
) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    assert "SECRET" not in repr(store)
    assert "SECRET" not in repr(uow)
    uow.calls.add(call)  # type: ignore[arg-type]
    with pytest.raises(PersistenceConflictError):
        uow.calls.add(replace(call, status=CallProcessingStatus.VALIDATED))  # type: ignore[arg-type]
    uow.knowledge.add_source(knowledge_source)  # type: ignore[arg-type]
    with pytest.raises(PersistenceConflictError):
        uow.knowledge.add_source(replace(knowledge_source, title="CHANGED"))  # type: ignore[arg-type]
    uow.rubrics.add(rubric)  # type: ignore[arg-type]
    with pytest.raises(PersistenceConflictError):
        uow.rubrics.add(replace(rubric, description="CHANGED"))  # type: ignore[arg-type]


def test_failure_injection_is_fake_only(
    call: object,
    transcription_result: object,
) -> None:
    store = InMemoryPersistenceStore()
    cfg = FakeFailureConfig(
        fail_operations=(
            FakeFailureOperation.CALLS_ADD,
            FakeFailureOperation.PROCESSING_ADD_TRANSCRIPTION,
        )
    )
    uow = InMemoryUnitOfWork(store=store, failure_config=cfg)
    with pytest.raises(RepositoryUnavailableError):
        uow.calls.add(call)  # type: ignore[arg-type]
    with pytest.raises(RepositoryUnavailableError):
        uow.processing_results.add_transcription(transcription_result)  # type: ignore[arg-type]
