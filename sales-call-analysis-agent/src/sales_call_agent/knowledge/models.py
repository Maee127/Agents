"""Immutable source-knowledge and rubric value contracts."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sales_call_agent.knowledge.exceptions import (
    InvalidKnowledgeSectionError,
    InvalidKnowledgeSourceError,
    InvalidRubricCriterionError,
    InvalidRubricError,
    InvalidScoringScaleError,
    InvalidSourceCitationError,
)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SAFE_WARNING_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LANGUAGE_TAG_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
_SEMVER_CORE_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class KnowledgeSourceType(StrEnum):
    """Approved source-document categories for knowledge extraction."""

    BOOK = "book"
    ARTICLE = "article"
    TRAINING_MANUAL = "training_manual"
    INTERNAL_POLICY = "internal_policy"
    SCRIPT = "script"
    CHECKLIST = "checklist"
    OTHER_APPROVED_DOCUMENT = "other_approved_document"


class KnowledgeSourceStatus(StrEnum):
    """Lifecycle status of a knowledge source record."""

    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class RubricStatus(StrEnum):
    """Lifecycle status of one rubric revision."""

    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class CriterionOrigin(StrEnum):
    """Provenance class for a criterion."""

    SOURCE_BACKED = "source_backed"
    ORGANIZATION_DEFINED = "organization_defined"


class RubricCriterionCategory(StrEnum):
    """Closed category set for sales-call rubric criteria."""

    OPENING = "opening"
    DISCOVERY = "discovery"
    NEEDS_ANALYSIS = "needs_analysis"
    QUALIFICATION = "qualification"
    VALUE_PRESENTATION = "value_presentation"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    FOLLOW_UP = "follow_up"
    COMMUNICATION = "communication"
    COMPLIANCE = "compliance"
    CUSTOM = "custom"


def _ensure_required_string(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise error(f"{field_name} must be non-empty and trimmed")


def _ensure_optional_string(value: object, field_name: str, error: type[Exception]) -> None:
    if value is not None:
        _ensure_required_string(value, field_name, error)


def _ensure_enum_member(
    value: object, enum_type: type[Enum], field_name: str, error: type[Exception]
) -> None:
    if not isinstance(value, enum_type):
        raise error(f"{field_name} must be a {enum_type.__name__} member")


def _ensure_safe_id(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe identifier")
    if "/" in value or "\\" in value or ":" in value:
        raise error(f"{field_name} must not contain path-like characters")


def _ensure_safe_warning_code(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SAFE_WARNING_CODE_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe warning code")


def _ensure_sha256(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SHA256_RE.fullmatch(value):
        raise error(f"{field_name} must be a lowercase SHA-256 hex string")


def _ensure_language_tag(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _LANGUAGE_TAG_RE.fullmatch(value):
        raise error(f"{field_name} must be a supported language tag")


def _ensure_semver_core(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SEMVER_CORE_RE.fullmatch(value):
        raise error(f"{field_name} must match MAJOR.MINOR.PATCH")


def _ensure_non_negative_integer(value: object, field_name: str, error: type[Exception]) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error(f"{field_name} must be an integer")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _ensure_positive_integer(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_non_negative_integer(value, field_name, error)
    assert isinstance(value, int)
    if value <= 0:
        raise error(f"{field_name} must be greater than zero")


def _ensure_finite_number(value: object, field_name: str, error: type[Exception]) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error(f"{field_name} must be a number")
    if not math.isfinite(value):
        raise error(f"{field_name} must be finite")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeSource:
    """Approved document metadata without local storage details."""

    source_id: str
    title: str = field(repr=False)
    source_type: KnowledgeSourceType
    status: KnowledgeSourceStatus
    author: str | None = None
    edition: str | None = None
    publication_year: int | None = None
    language: str = "en"
    content_hash: str
    version: str
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_id(self.source_id, "source_id", InvalidKnowledgeSourceError)
        _ensure_required_string(self.title, "title", InvalidKnowledgeSourceError)
        _ensure_enum_member(
            self.source_type, KnowledgeSourceType, "source_type", InvalidKnowledgeSourceError
        )
        _ensure_enum_member(
            self.status, KnowledgeSourceStatus, "status", InvalidKnowledgeSourceError
        )
        _ensure_optional_string(self.author, "author", InvalidKnowledgeSourceError)
        _ensure_optional_string(self.edition, "edition", InvalidKnowledgeSourceError)
        if self.publication_year is not None:
            _ensure_positive_integer(
                self.publication_year, "publication_year", InvalidKnowledgeSourceError
            )
        _ensure_language_tag(self.language, "language", InvalidKnowledgeSourceError)
        _ensure_sha256(self.content_hash, "content_hash", InvalidKnowledgeSourceError)
        _ensure_semver_core(self.version, "version", InvalidKnowledgeSourceError)
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidKnowledgeSourceError)


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeSection:
    """Traceable extracted text unit linked to one source."""

    section_id: str
    source_id: str
    heading: str | None = field(default=None, repr=False)
    text: str = field(repr=False)
    ordinal: int
    page_start: int | None = None
    page_end: int | None = None
    chapter: str | None = None
    content_hash: str
    language: str = "en"
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_id(self.section_id, "section_id", InvalidKnowledgeSectionError)
        _ensure_safe_id(self.source_id, "source_id", InvalidKnowledgeSectionError)
        _ensure_optional_string(self.heading, "heading", InvalidKnowledgeSectionError)
        _ensure_required_string(self.text, "text", InvalidKnowledgeSectionError)
        _ensure_non_negative_integer(self.ordinal, "ordinal", InvalidKnowledgeSectionError)
        if (self.page_start is None) != (self.page_end is None):
            raise InvalidKnowledgeSectionError(
                "page_start and page_end must be provided together"
            )
        if self.page_start is not None and self.page_end is not None:
            _ensure_positive_integer(self.page_start, "page_start", InvalidKnowledgeSectionError)
            _ensure_positive_integer(self.page_end, "page_end", InvalidKnowledgeSectionError)
            if self.page_end < self.page_start:
                raise InvalidKnowledgeSectionError("page_end must be >= page_start")
        _ensure_optional_string(self.chapter, "chapter", InvalidKnowledgeSectionError)
        _ensure_sha256(self.content_hash, "content_hash", InvalidKnowledgeSectionError)
        _ensure_language_tag(self.language, "language", InvalidKnowledgeSectionError)
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidKnowledgeSectionError)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceCitation:
    """Criterion-to-knowledge traceability link."""

    source_id: str
    section_id: str
    page_start: int | None = None
    page_end: int | None = None
    citation_note_code: str | None = None

    def __post_init__(self) -> None:
        _ensure_safe_id(self.source_id, "source_id", InvalidSourceCitationError)
        _ensure_safe_id(self.section_id, "section_id", InvalidSourceCitationError)
        if (self.page_start is None) != (self.page_end is None):
            raise InvalidSourceCitationError(
                "citation page_start and page_end must be provided together"
            )
        if self.page_start is not None and self.page_end is not None:
            _ensure_positive_integer(self.page_start, "page_start", InvalidSourceCitationError)
            _ensure_positive_integer(self.page_end, "page_end", InvalidSourceCitationError)
            if self.page_end < self.page_start:
                raise InvalidSourceCitationError("citation page_end must be >= page_start")
        if self.citation_note_code is not None:
            _ensure_safe_warning_code(
                self.citation_note_code, "citation_note_code", InvalidSourceCitationError
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class RubricScoreLevel:
    """One explicit score meaning in a criterion scoring scale."""

    score: float
    label: str
    description: str = field(repr=False)
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_finite_number(self.score, "score", InvalidScoringScaleError)
        _ensure_required_string(self.label, "label", InvalidScoringScaleError)
        _ensure_required_string(self.description, "description", InvalidScoringScaleError)
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidScoringScaleError)


@dataclass(frozen=True, slots=True, kw_only=True)
class RubricScoringScale:
    """Immutable criterion scoring scale."""

    scale_id: str
    name: str
    levels: tuple[RubricScoreLevel, ...]
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_id(self.scale_id, "scale_id", InvalidScoringScaleError)
        _ensure_required_string(self.name, "name", InvalidScoringScaleError)
        if not self.levels:
            raise InvalidScoringScaleError("levels must contain at least one score level")
        previous_score: float | None = None
        seen_scores: set[float] = set()
        for level in self.levels:
            if not isinstance(level, RubricScoreLevel):
                raise InvalidScoringScaleError("levels must contain RubricScoreLevel values")
            current_score = float(level.score)
            if current_score in seen_scores:
                raise InvalidScoringScaleError("score values must be unique")
            seen_scores.add(current_score)
            if previous_score is not None and current_score <= previous_score:
                raise InvalidScoringScaleError("score levels must be strictly increasing")
            previous_score = current_score
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidScoringScaleError)


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceRequirement:
    """Evaluation evidence policy for one rubric criterion."""

    transcript_evidence_required: bool = True
    timestamp_required: bool = True
    minimum_evidence_spans: int = 1
    seller_role_required: bool = True
    customer_context_required: bool = False
    absence_can_be_evidence: bool = False
    human_review_required: bool = False

    def __post_init__(self) -> None:
        for name in (
            "transcript_evidence_required",
            "timestamp_required",
            "seller_role_required",
            "customer_context_required",
            "absence_can_be_evidence",
            "human_review_required",
        ):
            if not isinstance(getattr(self, name), bool):
                raise InvalidRubricCriterionError(f"{name} must be a boolean")
        _ensure_non_negative_integer(
            self.minimum_evidence_spans,
            "minimum_evidence_spans",
            InvalidRubricCriterionError,
        )
        if not self.transcript_evidence_required:
            if self.timestamp_required:
                raise InvalidRubricCriterionError(
                    "timestamp_required must be false without transcript evidence"
                )
            if self.minimum_evidence_spans != 0:
                raise InvalidRubricCriterionError(
                    "minimum_evidence_spans must be zero without transcript evidence"
                )
        else:
            if self.minimum_evidence_spans < 1:
                raise InvalidRubricCriterionError(
                    "minimum_evidence_spans must be at least one with transcript evidence"
                )
            if self.timestamp_required is False and self.minimum_evidence_spans > 0:
                # Allowed: transcript evidence can be required without timestamps.
                pass


@dataclass(frozen=True, slots=True, kw_only=True)
class RubricCriterion:
    """One scoreable criterion definition for sales-call evaluation."""

    criterion_id: str
    name: str = field(repr=False)
    definition: str = field(repr=False)
    positive_guidance: str = field(repr=False)
    negative_guidance: str = field(repr=False)
    category: RubricCriterionCategory
    origin: CriterionOrigin
    weight: float
    scoring_scale: RubricScoringScale
    evidence_requirement: EvidenceRequirement
    source_citations: tuple[SourceCitation, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_id(self.criterion_id, "criterion_id", InvalidRubricCriterionError)
        _ensure_required_string(self.name, "name", InvalidRubricCriterionError)
        _ensure_required_string(self.definition, "definition", InvalidRubricCriterionError)
        _ensure_required_string(
            self.positive_guidance, "positive_guidance", InvalidRubricCriterionError
        )
        _ensure_required_string(
            self.negative_guidance, "negative_guidance", InvalidRubricCriterionError
        )
        _ensure_enum_member(
            self.category,
            RubricCriterionCategory,
            "category",
            InvalidRubricCriterionError,
        )
        _ensure_enum_member(self.origin, CriterionOrigin, "origin", InvalidRubricCriterionError)
        _ensure_finite_number(self.weight, "weight", InvalidRubricCriterionError)
        assert isinstance(self.weight, int | float)
        if self.weight <= 0:
            raise InvalidRubricCriterionError("weight must be greater than zero")
        if not isinstance(self.scoring_scale, RubricScoringScale):
            raise InvalidRubricCriterionError("scoring_scale must be a RubricScoringScale")
        if not isinstance(self.evidence_requirement, EvidenceRequirement):
            raise InvalidRubricCriterionError("evidence_requirement must be an EvidenceRequirement")
        for citation in self.source_citations:
            if not isinstance(citation, SourceCitation):
                raise InvalidRubricCriterionError(
                    "source_citations must contain SourceCitation values"
                )
        if self.origin is CriterionOrigin.SOURCE_BACKED and not self.source_citations:
            raise InvalidRubricCriterionError(
                "source_backed criteria require at least one source citation"
            )
        if self.origin is CriterionOrigin.ORGANIZATION_DEFINED and self.source_citations:
            raise InvalidRubricCriterionError(
                "organization_defined criteria must not include source citations"
            )
        _validate_citation_uniqueness(self.source_citations)
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidRubricCriterionError)


@dataclass(frozen=True, slots=True, kw_only=True)
class SalesRubric:
    """Versioned rubric revision value object."""

    rubric_id: str
    name: str = field(repr=False)
    version: str
    description: str = field(repr=False)
    language: str = "en"
    status: RubricStatus
    criteria: tuple[RubricCriterion, ...]
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_id(self.rubric_id, "rubric_id", InvalidRubricError)
        _ensure_required_string(self.name, "name", InvalidRubricError)
        _ensure_semver_core(self.version, "version", InvalidRubricError)
        _ensure_required_string(self.description, "description", InvalidRubricError)
        _ensure_language_tag(self.language, "language", InvalidRubricError)
        _ensure_enum_member(self.status, RubricStatus, "status", InvalidRubricError)
        seen_ids: set[str] = set()
        for criterion in self.criteria:
            if not isinstance(criterion, RubricCriterion):
                raise InvalidRubricError("criteria must contain RubricCriterion values")
            if criterion.criterion_id in seen_ids:
                raise InvalidRubricError("criterion IDs must be unique")
            seen_ids.add(criterion.criterion_id)
        if self.status is RubricStatus.DRAFT:
            pass
        elif not self.criteria:
            raise InvalidRubricError("approved and retired rubrics must contain criteria")
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidRubricError)

    @property
    def source_ids(self) -> tuple[str, ...]:
        """Sorted unique source IDs referenced by source-backed criteria."""
        source_ids = {
            citation.source_id
            for criterion in self.criteria
            if criterion.origin is CriterionOrigin.SOURCE_BACKED
            for citation in criterion.source_citations
        }
        return tuple(sorted(source_ids))


def _validate_citation_uniqueness(citations: Sequence[SourceCitation]) -> None:
    seen: set[tuple[str, str, int | None, int | None, str | None]] = set()
    for citation in citations:
        key = (
            citation.source_id,
            citation.section_id,
            citation.page_start,
            citation.page_end,
            citation.citation_note_code,
        )
        if key in seen:
            raise InvalidRubricCriterionError("source citations must be unique")
        seen.add(key)
