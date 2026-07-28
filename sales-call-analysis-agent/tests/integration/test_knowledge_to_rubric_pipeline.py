"""Integration-style deterministic knowledge-to-rubric assembly test."""

from __future__ import annotations

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
from sales_call_agent.knowledge.rubric import RubricBuildRequest, build_sales_rubric


def test_synthetic_knowledge_to_rubric_pipeline() -> None:
    source = KnowledgeSource(
        source_id="source_100",
        title="SECRET_SOURCE_TITLE_PIPELINE",
        source_type=KnowledgeSourceType.TRAINING_MANUAL,
        status=KnowledgeSourceStatus.APPROVED,
        content_hash="a" * 64,
        version="1.0.0",
        language="en",
    )
    section = KnowledgeSection(
        section_id="section_100",
        source_id="source_100",
        heading="SECRET_HEADING_PIPELINE",
        text="SECRET_TEXT_PIPELINE",
        ordinal=0,
        page_start=20,
        page_end=22,
        chapter="chapter_1",
        content_hash="b" * 64,
        language="en",
    )
    scale = RubricScoringScale(
        scale_id="scale_100",
        name="0-2 scale",
        levels=(
            RubricScoreLevel(score=0.0, label="poor", description="absent"),
            RubricScoreLevel(score=1.0, label="partial", description="some evidence"),
            RubricScoreLevel(score=2.0, label="strong", description="clear evidence"),
        ),
    )
    source_backed = RubricCriterion(
        criterion_id="criterion_100",
        name="SECRET_CRITERION_NAME_PIPELINE",
        definition="SECRET_DEFINITION_PIPELINE",
        positive_guidance="SECRET_POS_GUIDANCE_PIPELINE",
        negative_guidance="SECRET_NEG_GUIDANCE_PIPELINE",
        category=RubricCriterionCategory.DISCOVERY,
        origin=CriterionOrigin.SOURCE_BACKED,
        weight=1.0,
        scoring_scale=scale,
        evidence_requirement=EvidenceRequirement(),
        source_citations=(
            SourceCitation(
                source_id="source_100",
                section_id="section_100",
                page_start=21,
                page_end=21,
            ),
        ),
    )
    org_defined = RubricCriterion(
        criterion_id="criterion_200",
        name="SECRET_CRITERION_ORG",
        definition="SECRET_DEFINITION_ORG",
        positive_guidance="SECRET_POS_GUIDANCE_ORG",
        negative_guidance="SECRET_NEG_GUIDANCE_ORG",
        category=RubricCriterionCategory.COMPLIANCE,
        origin=CriterionOrigin.ORGANIZATION_DEFINED,
        weight=2.0,
        scoring_scale=scale,
        evidence_requirement=EvidenceRequirement(),
        source_citations=(),
    )
    request = RubricBuildRequest(
        sources=(source,),
        sections=(section,),
        rubric_id="rubric_100",
        name="SECRET_RUBRIC_NAME_PIPELINE",
        version="1.0.0",
        description="SECRET_RUBRIC_DESC_PIPELINE",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(source_backed, org_defined),
    )
    result_a = build_sales_rubric(request)
    result_b = build_sales_rubric(request)

    assert result_a == result_b
    assert result_a.source_ids == ("source_100",)
    assert result_a.criteria[0].source_citations[0].section_id == "section_100"
    assert result_a.criteria[1].origin is CriterionOrigin.ORGANIZATION_DEFINED
    assert result_a.version == "1.0.0"
    assert tuple(level.score for level in result_a.criteria[0].scoring_scale.levels) == (
        0.0,
        1.0,
        2.0,
    )
    rendered = repr(result_a)
    assert "SECRET_SOURCE_TITLE_PIPELINE" not in rendered
    assert "SECRET_TEXT_PIPELINE" not in rendered
    assert "SECRET_POS_GUIDANCE_PIPELINE" not in rendered
