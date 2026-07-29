"""Evaluation and call-score exact-key read routes.

Per-call list endpoints (GET /calls/{id}/evaluations and
GET /calls/{id}/call-scores) are intentionally omitted in v1:
  - no pagination contract defined;
  - potentially unbounded result sets;
  - provider/model identities in list responses could expose infrastructure
    details;
  - exact-key retrieval is sufficient for current use-cases.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.api.mappers import call_score_to_response, evaluation_to_response
from sales_call_agent.api.schemas.results import CallScoreResponse, EvaluationResponse
from sales_call_agent.persistence.keys import CallScoreKey, EvaluationKey


def create_results_router(deps: ApiDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["results"])

    @router.get("/evaluations", response_model=EvaluationResponse)
    def get_evaluation(
        call_id: str = Query(...),
        rubric_id: str = Query(...),
        rubric_version: str = Query(...),
        provider_name: str = Query(...),
        model_name: str = Query(...),
    ) -> EvaluationResponse:
        key = EvaluationKey(
            call_id=call_id,
            rubric_id=rubric_id,
            rubric_version=rubric_version,
            provider_name=provider_name,
            model_name=model_name,
        )
        uow = deps.unit_of_work_factory()
        result = uow.evaluations.get(key)
        return evaluation_to_response(result)

    @router.get("/call-scores", response_model=CallScoreResponse)
    def get_call_score(
        call_id: str = Query(...),
        rubric_id: str = Query(...),
        rubric_version: str = Query(...),
        provider_name: str = Query(...),
        model_name: str = Query(...),
        aggregation_policy_fingerprint: str = Query(...),
    ) -> CallScoreResponse:
        eval_key = EvaluationKey(
            call_id=call_id,
            rubric_id=rubric_id,
            rubric_version=rubric_version,
            provider_name=provider_name,
            model_name=model_name,
        )
        key = CallScoreKey(
            evaluation_key=eval_key,
            aggregation_policy_fingerprint=aggregation_policy_fingerprint,
        )
        uow = deps.unit_of_work_factory()
        result = uow.call_scores.get(key)
        return call_score_to_response(result, evaluation_key=eval_key)

    return router
