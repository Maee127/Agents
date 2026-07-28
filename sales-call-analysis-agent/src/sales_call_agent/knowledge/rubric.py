"""Deterministic rubric assembly for approved knowledge inputs."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sales_call_agent.knowledge.exceptions import RubricAssemblyError
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    KnowledgeSection,
    KnowledgeSource,
    KnowledgeSourceStatus,
    RubricCriterion,
    RubricStatus,
    SalesRubric,
    SourceCitation,
    _ensure_enum_member,
    _ensure_language_tag,
    _ensure_required_string,
    _ensure_safe_id,
    _ensure_safe_warning_code,
    _ensure_semver_core,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RubricBuildRequest:
    """Input bundle for deterministic rubric assembly."""

    sources: tuple[KnowledgeSource, ...] = field(repr=False)
    sections: tuple[KnowledgeSection, ...] = field(repr=False)
    rubric_id: str
    name: str = field(repr=False)
    version: str
    description: str = field(repr=False)
    language: str
    status: RubricStatus
    criteria: tuple[RubricCriterion, ...] = field(repr=False)
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_id(self.rubric_id, "rubric_id", RubricAssemblyError)
        _ensure_required_string(self.name, "name", RubricAssemblyError)
        _ensure_semver_core(self.version, "version", RubricAssemblyError)
        _ensure_required_string(self.description, "description", RubricAssemblyError)
        _ensure_language_tag(self.language, "language", RubricAssemblyError)
        _ensure_enum_member(self.status, RubricStatus, "status", RubricAssemblyError)
        for source in self.sources:
            if not isinstance(source, KnowledgeSource):
                raise RubricAssemblyError("sources must contain KnowledgeSource values")
        for section in self.sections:
            if not isinstance(section, KnowledgeSection):
                raise RubricAssemblyError("sections must contain KnowledgeSection values")
        for criterion in self.criteria:
            if not isinstance(criterion, RubricCriterion):
                raise RubricAssemblyError("criteria must contain RubricCriterion values")
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", RubricAssemblyError)


def build_sales_rubric(request: RubricBuildRequest) -> SalesRubric:
    """Build a validated SalesRubric from explicit authored criterion inputs."""
    if not isinstance(request, RubricBuildRequest):
        raise RubricAssemblyError("request must be a RubricBuildRequest")

    source_by_id = _unique_sources(request.sources)
    section_by_id = _unique_sections(request.sections)
    _validate_sections_belong_to_sources(section_by_id, source_by_id)
    _validate_unique_criterion_ids(request.criteria)

    normalized_criteria: list[RubricCriterion] = []
    for criterion in request.criteria:
        normalized_citations = tuple(sorted(criterion.source_citations, key=_citation_sort_key))
        _validate_citations(
            criterion=criterion,
            citations=normalized_citations,
            source_by_id=source_by_id,
            section_by_id=section_by_id,
            rubric_status=request.status,
        )
        normalized_criteria.append(replace(criterion, source_citations=normalized_citations))

    return SalesRubric(
        rubric_id=request.rubric_id,
        name=request.name,
        version=request.version,
        description=request.description,
        language=request.language,
        status=request.status,
        criteria=tuple(normalized_criteria),
        warning_codes=request.warning_codes,
    )


def _unique_sources(sources: tuple[KnowledgeSource, ...]) -> dict[str, KnowledgeSource]:
    source_by_id: dict[str, KnowledgeSource] = {}
    for source in sources:
        if source.source_id in source_by_id:
            raise RubricAssemblyError("source IDs must be unique")
        source_by_id[source.source_id] = source
    return source_by_id


def _unique_sections(sections: tuple[KnowledgeSection, ...]) -> dict[str, KnowledgeSection]:
    section_by_id: dict[str, KnowledgeSection] = {}
    for section in sections:
        if section.section_id in section_by_id:
            raise RubricAssemblyError("section IDs must be unique")
        section_by_id[section.section_id] = section
    return section_by_id


def _validate_sections_belong_to_sources(
    section_by_id: dict[str, KnowledgeSection],
    source_by_id: dict[str, KnowledgeSource],
) -> None:
    for section in section_by_id.values():
        if section.source_id not in source_by_id:
            raise RubricAssemblyError("each section must reference an included source")


def _validate_unique_criterion_ids(criteria: tuple[RubricCriterion, ...]) -> None:
    seen_ids: set[str] = set()
    for criterion in criteria:
        if criterion.criterion_id in seen_ids:
            raise RubricAssemblyError("criterion IDs must be unique")
        seen_ids.add(criterion.criterion_id)


def _validate_citations(
    *,
    criterion: RubricCriterion,
    citations: tuple[SourceCitation, ...],
    source_by_id: dict[str, KnowledgeSource],
    section_by_id: dict[str, KnowledgeSection],
    rubric_status: RubricStatus,
) -> None:
    if criterion.origin is CriterionOrigin.SOURCE_BACKED and not citations:
        raise RubricAssemblyError("source-backed criteria require source citations")
    if criterion.origin is CriterionOrigin.ORGANIZATION_DEFINED and citations:
        raise RubricAssemblyError("organization-defined criteria must not include citations")

    for citation in citations:
        source = source_by_id.get(citation.source_id)
        if source is None:
            raise RubricAssemblyError("citation source must exist in build request sources")
        section = section_by_id.get(citation.section_id)
        if section is None:
            raise RubricAssemblyError("citation section must exist in build request sections")
        if section.source_id != citation.source_id:
            raise RubricAssemblyError("citation section must belong to citation source")
        if (
            citation.page_start is not None
            and citation.page_end is not None
            and section.page_start is not None
            and section.page_end is not None
            and (citation.page_start < section.page_start or citation.page_end > section.page_end)
        ):
            raise RubricAssemblyError("citation page range must fit inside section page range")
        if (
            rubric_status is RubricStatus.APPROVED
            and source.status is not KnowledgeSourceStatus.APPROVED
        ):
            raise RubricAssemblyError("approved rubrics may cite only approved sources")


def _citation_sort_key(citation: SourceCitation) -> tuple[str, str, int, int, str]:
    return (
        citation.source_id,
        citation.section_id,
        citation.page_start if citation.page_start is not None else -1,
        citation.page_end if citation.page_end is not None else -1,
        citation.citation_note_code or "",
    )
