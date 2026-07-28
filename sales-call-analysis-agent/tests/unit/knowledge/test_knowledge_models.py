"""Unit tests for knowledge source, section, and citation models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from sales_call_agent.knowledge.exceptions import (
    InvalidKnowledgeSectionError,
    InvalidKnowledgeSourceError,
    InvalidSourceCitationError,
)
from sales_call_agent.knowledge.models import (
    KnowledgeSection,
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    SourceCitation,
)


def test_source_status_requires_enum() -> None:
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="source_001",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=cast(Any, "approved"),
            content_hash="a" * 64,
            version="1.0.0",
            language="en",
        )


def test_strict_sha256_validation() -> None:
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="source_001",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=KnowledgeSourceStatus.APPROVED,
            content_hash="A" * 64,
            version="1.0.0",
            language="en",
        )
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="source_001",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=KnowledgeSourceStatus.APPROVED,
            content_hash="a" * 63,
            version="1.0.0",
            language="en",
        )
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="source_001",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=KnowledgeSourceStatus.APPROVED,
            content_hash="g" * 64,
            version="1.0.0",
            language="en",
        )
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="source_001",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=KnowledgeSourceStatus.APPROVED,
            content_hash=" " + ("a" * 64),
            version="1.0.0",
            language="en",
        )


@pytest.mark.parametrize("language", ["en", "fa", "en-US", "fa-IR"])
def test_language_tag_validation_valid(language: str) -> None:
    source = KnowledgeSource(
        source_id="source_001",
        title="Title",
        source_type=KnowledgeSourceType.BOOK,
        status=KnowledgeSourceStatus.APPROVED,
        content_hash="a" * 64,
        version="1.0.0",
        language=language,
    )
    assert source.language == language


@pytest.mark.parametrize("language", ["", " en", "en-us", "EN", "english"])
def test_language_tag_validation_invalid(language: str) -> None:
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="source_001",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=KnowledgeSourceStatus.APPROVED,
            content_hash="a" * 64,
            version="1.0.0",
            language=language,
        )


def test_safe_identifier_validation_rejects_paths() -> None:
    with pytest.raises(InvalidKnowledgeSourceError):
        KnowledgeSource(
            source_id="C:/secret/path",
            title="Title",
            source_type=KnowledgeSourceType.BOOK,
            status=KnowledgeSourceStatus.APPROVED,
            content_hash="a" * 64,
            version="1.0.0",
            language="en",
        )


def test_section_repr_hides_text_and_heading(approved_section: KnowledgeSection) -> None:
    rendered = repr(approved_section)
    assert "SECRET_SECTION_TEXT_ALPHA" not in rendered
    assert "SECRET_HEADING_ALPHA" not in rendered


def test_section_hash_validation_matches_source_rules() -> None:
    with pytest.raises(InvalidKnowledgeSectionError):
        KnowledgeSection(
            section_id="section_001",
            source_id="source_001",
            heading="Heading",
            text="Text",
            ordinal=0,
            content_hash="A" * 64,
            language="en",
        )


def test_section_page_bounds_validation() -> None:
    with pytest.raises(InvalidKnowledgeSectionError):
        KnowledgeSection(
            section_id="section_001",
            source_id="source_001",
            heading="Heading",
            text="Text",
            ordinal=0,
            page_start=10,
            content_hash="b" * 64,
            language="en",
        )


def test_citation_page_bounds_validation() -> None:
    with pytest.raises(InvalidSourceCitationError):
        SourceCitation(source_id="source_001", section_id="section_001", page_start=3)
    with pytest.raises(InvalidSourceCitationError):
        SourceCitation(
            source_id="source_001",
            section_id="section_001",
            page_start=5,
            page_end=4,
        )


def test_models_are_frozen(approved_source: KnowledgeSource) -> None:
    with pytest.raises(FrozenInstanceError):
        approved_source.status = KnowledgeSourceStatus.RETIRED  # type: ignore[misc]
