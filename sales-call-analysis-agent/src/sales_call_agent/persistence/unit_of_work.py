"""Provider-independent unit-of-work protocol for persistence operations."""

from __future__ import annotations

from typing import Protocol

from sales_call_agent.persistence.repositories import (
    CallProcessingResultRepository,
    CallRepository,
    CallScoreRepository,
    EvaluationRepository,
    KnowledgeRepository,
    RubricRepository,
)


class UnitOfWork(Protocol):
    """Atomic persistence boundary for repository operations."""

    calls: CallRepository
    processing_results: CallProcessingResultRepository
    knowledge: KnowledgeRepository
    rubrics: RubricRepository
    evaluations: EvaluationRepository
    call_scores: CallScoreRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
