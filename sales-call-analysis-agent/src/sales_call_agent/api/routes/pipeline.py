"""Pipeline run route."""

from __future__ import annotations

from fastapi import APIRouter

from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.api.mappers import pipeline_result_to_response, pipeline_run_request_to_domain
from sales_call_agent.api.schemas.pipeline import PipelineRunRequest, PipelineRunResponse
from sales_call_agent.orchestration.engine import run_call_pipeline


def create_pipeline_router(deps: ApiDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/v1/pipeline-runs", tags=["pipeline"])

    @router.post("", response_model=PipelineRunResponse)
    def run_pipeline(req: PipelineRunRequest) -> PipelineRunResponse:
        domain_req = pipeline_run_request_to_domain(req)
        result = run_call_pipeline(domain_req, deps.pipeline_dependencies)
        return pipeline_result_to_response(result)

    return router
