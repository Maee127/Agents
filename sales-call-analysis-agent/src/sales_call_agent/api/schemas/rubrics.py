"""Rubric summary response schemas (privacy-first: no definitions or source text)."""

from __future__ import annotations

from sales_call_agent.api.schemas.common import StrictApiModel


class RubricRevisionSummary(StrictApiModel):
    """Privacy-safe summary of one rubric revision."""

    rubric_id: str
    version: str
    status: str
    revision: int
    criterion_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    language: str | None = None


class RubricRevisionListResponse(StrictApiModel):
    """Response for GET /api/v1/rubrics/{rubric_id}."""

    rubric_id: str
    revisions: tuple[RubricRevisionSummary, ...]
