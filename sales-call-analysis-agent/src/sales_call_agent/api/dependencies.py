"""API dependency container for the v1 application."""

from __future__ import annotations

from dataclasses import dataclass, field

from sales_call_agent.orchestration.dependencies import PipelineDependencies, UnitOfWorkFactory


@dataclass(frozen=True, slots=True, kw_only=True)
class ApiDependencies:
    """Frozen dependency container for the API layer.

    Both fields are excluded from repr to prevent credential/provider leakage.
    """

    unit_of_work_factory: UnitOfWorkFactory = field(repr=False)
    pipeline_dependencies: PipelineDependencies = field(repr=False)
