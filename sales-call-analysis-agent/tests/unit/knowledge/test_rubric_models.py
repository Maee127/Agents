"""Unit tests for rubric models and local invariants."""

from __future__ import annotations

from dataclasses import fields

import pytest

from sales_call_agent.knowledge.exceptions import (
    InvalidRubricCriterionError,
    InvalidRubricError,
    InvalidScoringScaleError,
)
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    RubricCriterion,
    RubricCriterionCategory,
    RubricScoreLevel,
    RubricScoringScale,
    RubricStatus,
    SalesRubric,
    SourceCitation,
)


def test_score_level_has_no_evidence_count_field() -> None:
    assert {current.name for current in fields(RubricScoreLevel)} == {
        "score",
        "label",
        "description",
        "warning_codes",
    }


def test_unordered_score_levels_rejected() -> None:
    with pytest.raises(InvalidScoringScaleError, match="strictly increasing"):
        RubricScoringScale(
            scale_id="scale_001",
            name="scale",
            levels=(
                RubricScoreLevel(score=1.0, label="a", description="A"),
                RubricScoreLevel(score=0.0, label="b", description="B"),
            ),
        )


def test_evidence_requirement_strict_rules() -> None:
    with pytest.raises(InvalidRubricCriterionError, match="timestamp_required"):
        EvidenceRequirement(transcript_evidence_required=False, timestamp_required=True)
    with pytest.raises(InvalidRubricCriterionError, match="minimum_evidence_spans must be zero"):
        EvidenceRequirement(
            transcript_evidence_required=False,
            timestamp_required=False,
            minimum_evidence_spans=1,
        )
    with pytest.raises(
        InvalidRubricCriterionError,
        match="minimum_evidence_spans must be at least one",
    ):
        EvidenceRequirement(transcript_evidence_required=True, minimum_evidence_spans=0)


def test_zero_weight_rejected(score_scale: RubricScoringScale) -> None:
    with pytest.raises(InvalidRubricCriterionError, match="greater than zero"):
        RubricCriterion(
            criterion_id="criterion_001",
            name="name",
            definition="def",
            positive_guidance="pos",
            negative_guidance="neg",
            category=RubricCriterionCategory.OPENING,
            origin=CriterionOrigin.ORGANIZATION_DEFINED,
            weight=0.0,
            scoring_scale=score_scale,
            evidence_requirement=EvidenceRequirement(),
        )


def test_organization_defined_with_citations_rejected(score_scale: RubricScoringScale) -> None:
    with pytest.raises(InvalidRubricCriterionError, match="must not include"):
        RubricCriterion(
            criterion_id="criterion_001",
            name="name",
            definition="def",
            positive_guidance="pos",
            negative_guidance="neg",
            category=RubricCriterionCategory.OPENING,
            origin=CriterionOrigin.ORGANIZATION_DEFINED,
            weight=1.0,
            scoring_scale=score_scale,
            evidence_requirement=EvidenceRequirement(),
            source_citations=(SourceCitation(source_id="source_001", section_id="section_001"),),
        )


def test_source_backed_without_citations_rejected(score_scale: RubricScoringScale) -> None:
    with pytest.raises(InvalidRubricCriterionError, match="require at least one"):
        RubricCriterion(
            criterion_id="criterion_001",
            name="name",
            definition="def",
            positive_guidance="pos",
            negative_guidance="neg",
            category=RubricCriterionCategory.OPENING,
            origin=CriterionOrigin.SOURCE_BACKED,
            weight=1.0,
            scoring_scale=score_scale,
            evidence_requirement=EvidenceRequirement(),
        )


def test_sales_rubric_source_ids_computed(source_backed_criterion: RubricCriterion) -> None:
    rubric = SalesRubric(
        rubric_id="rubric_001",
        name="SECRET_RUBRIC_NAME",
        version="1.0.0",
        description="SECRET_RUBRIC_DESCRIPTION",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(source_backed_criterion,),
    )
    assert "created_from_source_ids" not in {current.name for current in fields(SalesRubric)}
    assert rubric.source_ids == ("source_001",)


def test_rubric_status_empty_behavior(score_scale: RubricScoringScale) -> None:
    draft = SalesRubric(
        rubric_id="rubric_001",
        name="name",
        version="1.0.0",
        description="desc",
        language="en",
        status=RubricStatus.DRAFT,
        criteria=(),
    )
    assert draft.criteria == ()
    with pytest.raises(InvalidRubricError, match="must contain criteria"):
        SalesRubric(
            rubric_id="rubric_001",
            name="name",
            version="1.0.0",
            description="desc",
            language="en",
            status=RubricStatus.APPROVED,
            criteria=(),
        )
    with pytest.raises(InvalidRubricError, match="must contain criteria"):
        SalesRubric(
            rubric_id="rubric_001",
            name="name",
            version="1.0.0",
            description="desc",
            language="en",
            status=RubricStatus.RETIRED,
            criteria=(),
        )


@pytest.mark.parametrize("version", ["1.0.0", "0.1.0"])
def test_semver_valid(version: str, source_backed_criterion: RubricCriterion) -> None:
    rubric = SalesRubric(
        rubric_id="rubric_001",
        name="name",
        version=version,
        description="desc",
        language="en",
        status=RubricStatus.APPROVED,
        criteria=(source_backed_criterion,),
    )
    assert rubric.version == version


@pytest.mark.parametrize("version", ["v1.0.0", "1.0", "01.0.0", "1.0.0-beta", " 1.0.0"])
def test_semver_invalid(version: str, source_backed_criterion: RubricCriterion) -> None:
    with pytest.raises(InvalidRubricError):
        SalesRubric(
            rubric_id="rubric_001",
            name="name",
            version=version,
            description="desc",
            language="en",
            status=RubricStatus.APPROVED,
            criteria=(source_backed_criterion,),
        )
