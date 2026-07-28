"""Protocol-shape tests for persistence repository contracts."""

from __future__ import annotations

from sales_call_agent.persistence.fake import InMemoryPersistenceStore, InMemoryUnitOfWork
from sales_call_agent.persistence.repositories import (
    CallProcessingResultRepository,
    CallRepository,
    CallScoreRepository,
    EvaluationRepository,
    KnowledgeRepository,
    RubricRepository,
)


def test_fake_repositories_structurally_satisfy_protocols() -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    calls_repo: CallRepository = uow.calls
    processing_repo: CallProcessingResultRepository = uow.processing_results
    knowledge_repo: KnowledgeRepository = uow.knowledge
    rubric_repo: RubricRepository = uow.rubrics
    evaluation_repo: EvaluationRepository = uow.evaluations
    score_repo: CallScoreRepository = uow.call_scores
    assert calls_repo is not None
    assert processing_repo is not None
    assert knowledge_repo is not None
    assert rubric_repo is not None
    assert evaluation_repo is not None
    assert score_repo is not None
    assert not hasattr(processing_repo, "list_completed_call_ids")
