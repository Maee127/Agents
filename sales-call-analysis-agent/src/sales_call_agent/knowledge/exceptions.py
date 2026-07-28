"""Knowledge and rubric exception hierarchy.

All messages are log-safe and must not expose proprietary source text or paths.
"""

from sales_call_agent.domain.exceptions import DomainError


class KnowledgeError(DomainError):
    """Base class for knowledge/rubric validation failures."""


class InvalidKnowledgeSourceError(KnowledgeError):
    """Raised when a KnowledgeSource invariant is violated."""


class InvalidKnowledgeSectionError(KnowledgeError):
    """Raised when a KnowledgeSection invariant is violated."""


class InvalidSourceCitationError(KnowledgeError):
    """Raised when a SourceCitation invariant is violated."""


class InvalidRubricError(KnowledgeError):
    """Raised when a SalesRubric invariant is violated."""


class InvalidRubricCriterionError(KnowledgeError):
    """Raised when a RubricCriterion invariant is violated."""


class InvalidScoringScaleError(KnowledgeError):
    """Raised when scoring-scale or score-level invariants are violated."""


class RubricAssemblyError(KnowledgeError):
    """Raised when rubric assembly references are missing or inconsistent."""
