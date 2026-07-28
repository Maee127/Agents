"""Persistence-specific immutable versioned record wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field

from sales_call_agent.domain.models import Call
from sales_call_agent.knowledge.models import KnowledgeSource, SalesRubric
from sales_call_agent.persistence.exceptions import InvalidPersistenceInputError


def _ensure_revision(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidPersistenceInputError(f"{field_name} must be an integer")
    if value < 1:
        raise InvalidPersistenceInputError(f"{field_name} must be at least 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionedCallRecord:
    """Versioned wrapper for mutable call aggregate persistence."""

    value: Call = field(repr=False)
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, Call):
            raise InvalidPersistenceInputError("value must be a Call")
        _ensure_revision(self.revision, "revision")


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionedKnowledgeSourceRecord:
    """Versioned wrapper for knowledge-source lifecycle updates."""

    value: KnowledgeSource = field(repr=False)
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, KnowledgeSource):
            raise InvalidPersistenceInputError("value must be a KnowledgeSource")
        _ensure_revision(self.revision, "revision")


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionedRubricRecord:
    """Versioned wrapper for rubric status transitions."""

    value: SalesRubric = field(repr=False)
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, SalesRubric):
            raise InvalidPersistenceInputError("value must be a SalesRubric")
        _ensure_revision(self.revision, "revision")
