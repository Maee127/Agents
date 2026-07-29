"""Application factory for the v1 Sales Call Analysis API.

No module-level ``app`` instance exists.  The factory must be called with
explicit dependencies; it does not read from ``app.state`` or globals.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.api.errors import register_exception_handlers
from sales_call_agent.api.routes.calls import create_calls_router
from sales_call_agent.api.routes.pipeline import create_pipeline_router
from sales_call_agent.api.routes.results import create_results_router
from sales_call_agent.api.routes.rubrics import create_rubrics_router

_OPENAPI_DESCRIPTION = (
    "Sales Call Analysis API v1 — local, synchronous, deployment-neutral.\n\n"
    "This API is an internal operational boundary; it is not a public SaaS "
    "endpoint.  Authentication, tenancy, worker execution, and cloud deployment "
    "remain future work.  Provider and model identities in query parameters are "
    "internal result identifiers — they do not select or override configured "
    "providers."
)


def create_app(dependencies: ApiDependencies) -> FastAPI:
    """Create a configured FastAPI application bound to the given dependencies.

    The factory accepts an explicit dependency container so that tests and
    different environments can wire different stores and providers without
    global state.  No module-level app instance is created.
    """
    app = FastAPI(
        title="Sales Call Analysis API",
        version="1",
        description=_OPENAPI_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    register_exception_handlers(app)

    app.include_router(create_calls_router(dependencies))
    app.include_router(create_pipeline_router(dependencies))
    app.include_router(create_rubrics_router(dependencies))
    app.include_router(create_results_router(dependencies))

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app
