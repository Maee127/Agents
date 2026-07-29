"""Rubric read routes."""

from __future__ import annotations

from fastapi import APIRouter

from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.api.mappers import versioned_rubric_to_summary
from sales_call_agent.api.schemas.rubrics import RubricRevisionListResponse, RubricRevisionSummary


def create_rubrics_router(deps: ApiDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rubrics", tags=["rubrics"])

    @router.get("/{rubric_id}", response_model=RubricRevisionListResponse)
    def list_rubric_revisions(rubric_id: str) -> RubricRevisionListResponse:
        uow = deps.unit_of_work_factory()
        records = uow.rubrics.list_versions(rubric_id)
        return RubricRevisionListResponse(
            rubric_id=rubric_id,
            revisions=tuple(versioned_rubric_to_summary(r) for r in records),
        )

    @router.get("/{rubric_id}/{version}", response_model=RubricRevisionSummary)
    def get_rubric_revision(rubric_id: str, version: str) -> RubricRevisionSummary:
        uow = deps.unit_of_work_factory()
        record = uow.rubrics.get(rubric_id, version)
        return versioned_rubric_to_summary(record)

    return router
