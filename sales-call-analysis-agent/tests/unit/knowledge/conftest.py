"""Shared fixtures for knowledge and rubric unit tests."""

from __future__ import annotations

import pytest

from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    KnowledgeSection,
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    RubricCriterion,
    RubricCriterionCategory,
    RubricScoreLevel,
    RubricScoringScale,
    RubricStatus,
    SourceCitation,
)
from sales_call_agent.knowledge.rubric import RubricBuildRequest


@pytest.fixture
def approved_source() -> KnowledgeSource:
    return KnowledgeSource(
        source_id="source_001",
        title="SECRET_SOURCE_TITLE_ALPHA",
        source_type=KnowledgeSourceType.BOOK,
        status=KnowledgeSourceStatus.APPROVED,
        content_hash="a" * 64,
        version="1.0.0",
        language="en",
    )


@pytest.fixture
def approved_section() -> KnowledgeSection:
    return KnowledgeSection(
        section_id="section_001",
        source_id="source_001",
        heading="SECRET_HEADING_ALPHA",
        text="SECRET_SECTION_TEXT_ALPHA",
        ordinal=0,
        page_start=10,
        page_end=12,
        content_hash="b" * 64,
        language="en",
    )


@pytest.fixture
def score_scale() -> RubricScoringScale:
    return RubricScoringScale(
        scale_id="scale_002",
        name="Binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="missing behavior"),
            RubricScoreLevel(score=1.0, label="yes", description="present behavior"),
        ),
    )


@pytest.fixture
def source_backed_criterion(score_scale: RubricScoringScale) -> RubricCriterion:
    return RubricCriterion(
        criterion_id="criterion_001",
        name="SECRET_CRITERION_NAME_ONE",
        definition="SECRET_DEFINITION_ONE",
        positive_guidance="SECRET_POSITIVE_GUIDANCE_ONE",
        negative_guidance="SECRET_NEGATIVE_GUIDANCE_ONE",
        category=RubricCriterionCategory.DISCOVERY,
        origin=CriterionOrigin.SOURCE_BACKED,
        weight=1.5,
        scoring_scale=score_scale,
        evidence_requirement=EvidenceRequirement(),
        source_citations=(
            SourceCitation(
                source_id="source_001",
                section_id="section_001",
                page_start=10,
                page_end=10,
            ),
        ),
    )


@pytest.fixture
def organization_criterion(score_scale: RubricScoringScale) -> RubricCriterion:
    return RubricCriterion(
        criterion_id="criterion_002",
        name="SECRET_CRITERION_NAME_TWO",
        definition="SECRET_DEFINITION_TWO",
        positive_guidance="SECRET_POSITIVE_GUIDANCE_TWO",
        negative_guidance="SECRET_NEGATIVE_GUIDANCE_TWO",
        category=RubricCriterionCategory.COMPLIANCE,
        origin=CriterionOrigin.ORGANIZATION_DEFINED,
        weight=2.0,
        scoring_scale=score_scale,
        evidence_requirement=EvidenceRequirement(),
        source_citations=(),
    )


@pytest.fixture
def build_request(
    approved_source: KnowledgeSource,
    approved_section: KnowledgeSection,
    source_backed_criterion: RubricCriterion,
) -> RubricBuildRequest:
    return RubricBuildRequest(
        sources=(approved_source,),
        sections=(approved_section,),
        rubric_id="rubric_001",
        name="SECRET_RUBRIC_NAME",
        version="1.0.0",
        description="SECRET_RUBRIC_DESCRIPTION",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(source_backed_criterion,),
    )
