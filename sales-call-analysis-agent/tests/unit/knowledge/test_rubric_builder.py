"""Unit tests for deterministic rubric assembly."""

from __future__ import annotations

import pytest

from sales_call_agent.knowledge.exceptions import RubricAssemblyError
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    KnowledgeSection,
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    RubricCriterion,
    RubricCriterionCategory,
    RubricStatus,
    SourceCitation,
)
from sales_call_agent.knowledge.rubric import RubricBuildRequest, build_sales_rubric


def test_build_valid_source_backed_rubric(build_request: RubricBuildRequest) -> None:
    rubric = build_sales_rubric(build_request)
    assert rubric.rubric_id == "rubric_001"
    assert rubric.source_ids == ("source_001",)


def test_build_valid_organization_only_rubric(organization_criterion: RubricCriterion) -> None:
    rubric = build_sales_rubric(
        RubricBuildRequest(
            sources=(),
            sections=(),
            rubric_id="rubric_010",
            name="SECRET_RUBRIC_NAME",
            version="1.0.0",
            description="SECRET_RUBRIC_DESCRIPTION",
            language="en",
            status=RubricStatus.APPROVED,
            criteria=(organization_criterion,),
        )
    )
    assert rubric.source_ids == ()


def test_retired_source_cannot_support_newly_approved_rubric(
    build_request: RubricBuildRequest,
    approved_source: KnowledgeSource,
) -> None:
    retired = KnowledgeSource(
        source_id=approved_source.source_id,
        title="SECRET_SOURCE_TITLE_ALPHA",
        source_type=KnowledgeSourceType.BOOK,
        status=KnowledgeSourceStatus.RETIRED,
        content_hash=approved_source.content_hash,
        version=approved_source.version,
        language=approved_source.language,
    )
    request = RubricBuildRequest(
        sources=(retired,),
        sections=build_request.sections,
        rubric_id=build_request.rubric_id,
        name=build_request.name,
        version=build_request.version,
        description=build_request.description,
        language=build_request.language,
        status=RubricStatus.APPROVED,
        criteria=build_request.criteria,
    )
    with pytest.raises(RubricAssemblyError, match="only approved sources"):
        build_sales_rubric(request)


def test_missing_source_rejected(
    approved_section: KnowledgeSection,
    source_backed_criterion: RubricCriterion,
) -> None:
    with pytest.raises(RubricAssemblyError, match="included source"):
        build_sales_rubric(
            RubricBuildRequest(
                sources=(),
                sections=(approved_section,),
                rubric_id="rubric_001",
                name="name",
                version="1.0.0",
                description="desc",
                language="en",
                status=RubricStatus.DRAFT,
                criteria=(source_backed_criterion,),
            )
        )


def test_missing_section_rejected(
    approved_source: KnowledgeSource,
    source_backed_criterion: RubricCriterion,
) -> None:
    with pytest.raises(RubricAssemblyError, match="section must exist"):
        build_sales_rubric(
            RubricBuildRequest(
                sources=(approved_source,),
                sections=(),
                rubric_id="rubric_001",
                name="name",
                version="1.0.0",
                description="desc",
                language="en",
                status=RubricStatus.DRAFT,
                criteria=(source_backed_criterion,),
            )
        )


def test_cross_source_citation_mismatch_rejected(
    approved_source: KnowledgeSource,
    approved_section: KnowledgeSection,
    source_backed_criterion: RubricCriterion,
) -> None:
    second_source = KnowledgeSource(
        source_id="source_002",
        title="SECRET_SOURCE_TITLE_TWO",
        source_type=KnowledgeSourceType.INTERNAL_POLICY,
        status=KnowledgeSourceStatus.APPROVED,
        content_hash="c" * 64,
        version="1.0.0",
        language="en",
    )
    mismatched = RubricCriterion(
        criterion_id=source_backed_criterion.criterion_id,
        name=source_backed_criterion.name,
        definition=source_backed_criterion.definition,
        positive_guidance=source_backed_criterion.positive_guidance,
        negative_guidance=source_backed_criterion.negative_guidance,
        category=source_backed_criterion.category,
        origin=source_backed_criterion.origin,
        weight=source_backed_criterion.weight,
        scoring_scale=source_backed_criterion.scoring_scale,
        evidence_requirement=source_backed_criterion.evidence_requirement,
        source_citations=(SourceCitation(source_id="source_002", section_id="section_001"),),
    )
    with pytest.raises(RubricAssemblyError, match="must belong to citation source"):
        build_sales_rubric(
            RubricBuildRequest(
                sources=(approved_source, second_source),
                sections=(approved_section,),
                rubric_id="rubric_001",
                name="name",
                version="1.0.0",
                description="desc",
                language="en",
                status=RubricStatus.DRAFT,
                criteria=(mismatched,),
            )
        )


def test_citation_page_range_must_fit_inside_section_page_range(
    approved_source: KnowledgeSource,
    approved_section: KnowledgeSection,
    source_backed_criterion: RubricCriterion,
) -> None:
    out_of_range = RubricCriterion(
        criterion_id=source_backed_criterion.criterion_id,
        name=source_backed_criterion.name,
        definition=source_backed_criterion.definition,
        positive_guidance=source_backed_criterion.positive_guidance,
        negative_guidance=source_backed_criterion.negative_guidance,
        category=source_backed_criterion.category,
        origin=source_backed_criterion.origin,
        weight=source_backed_criterion.weight,
        scoring_scale=source_backed_criterion.scoring_scale,
        evidence_requirement=source_backed_criterion.evidence_requirement,
        source_citations=(
            SourceCitation(
                source_id="source_001",
                section_id="section_001",
                page_start=9,
                page_end=9,
            ),
        ),
    )
    with pytest.raises(RubricAssemblyError, match="fit inside"):
        build_sales_rubric(
            RubricBuildRequest(
                sources=(approved_source,),
                sections=(approved_section,),
                rubric_id="rubric_001",
                name="name",
                version="1.0.0",
                description="desc",
                language="en",
                status=RubricStatus.DRAFT,
                criteria=(out_of_range,),
            )
        )


def test_criterion_order_preserved(
    approved_source: KnowledgeSource,
    approved_section: KnowledgeSection,
    source_backed_criterion: RubricCriterion,
) -> None:
    second = RubricCriterion(
        criterion_id="criterion_999",
        name="SECRET_CRITERION_BETA",
        definition="def",
        positive_guidance="pos",
        negative_guidance="neg",
        category=RubricCriterionCategory.CLOSING,
        origin=CriterionOrigin.SOURCE_BACKED,
        weight=1.0,
        scoring_scale=source_backed_criterion.scoring_scale,
        evidence_requirement=EvidenceRequirement(),
        source_citations=(SourceCitation(source_id="source_001", section_id="section_001"),),
    )
    request_a = RubricBuildRequest(
        sources=(approved_source,),
        sections=(approved_section,),
        rubric_id="rubric_001",
        name="name",
        version="1.0.0",
        description="desc",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(source_backed_criterion, second),
    )
    request_b = RubricBuildRequest(
        sources=(approved_source,),
        sections=(approved_section,),
        rubric_id="rubric_001",
        name="name",
        version="1.0.0",
        description="desc",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(second, source_backed_criterion),
    )
    result_a = build_sales_rubric(request_a)
    result_b = build_sales_rubric(request_b)
    assert tuple(item.criterion_id for item in result_a.criteria) == (
        source_backed_criterion.criterion_id,
        second.criterion_id,
    )
    assert tuple(item.criterion_id for item in result_b.criteria) == (
        second.criterion_id,
        source_backed_criterion.criterion_id,
    )


def test_repeated_builds_compare_equal(build_request: RubricBuildRequest) -> None:
    first = build_sales_rubric(build_request)
    second = build_sales_rubric(build_request)
    assert first == second


def test_proprietary_text_not_in_exceptions(
    source_backed_criterion: RubricCriterion,
) -> None:
    proprietary = "SECRET_PROPRIETARY_GUIDANCE_NEVER_LEAK"
    criterion = RubricCriterion(
        criterion_id="criterion_123",
        name=proprietary,
        definition=proprietary,
        positive_guidance=proprietary,
        negative_guidance=proprietary,
        category=RubricCriterionCategory.DISCOVERY,
        origin=CriterionOrigin.SOURCE_BACKED,
        weight=1.0,
        scoring_scale=source_backed_criterion.scoring_scale,
        evidence_requirement=EvidenceRequirement(),
        source_citations=(SourceCitation(source_id="source_999", section_id="section_999"),),
    )
    request = RubricBuildRequest(
        sources=(),
        sections=(),
        rubric_id="rubric_001",
        name=proprietary,
        version="1.0.0",
        description=proprietary,
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(criterion,),
    )
    with pytest.raises(RubricAssemblyError) as exc_info:
        build_sales_rubric(request)
    message = str(exc_info.value)
    assert proprietary not in message
