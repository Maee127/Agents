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

    @property
    def calls(self) -> CallRepository: ...

    @property
    def processing_results(self) -> CallProcessingResultRepository: ...

    @property
    def knowledge(self) -> KnowledgeRepository: ...

    @property
    def rubrics(self) -> RubricRepository: ...

    @property
    def evaluations(self) -> EvaluationRepository: ...

    @property
    def call_scores(self) -> CallScoreRepository: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
