"""Regression tests for import-cycle safety across aggregation packages."""

from __future__ import annotations

import subprocess
import sys


def _import_in_order(first: str, second: str) -> None:
    code = (
        f"import importlib; importlib.import_module({first!r}); importlib.import_module({second!r})"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )


def test_import_aggregation_models_then_evaluation_models_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.aggregation.models",
        "sales_call_agent.evaluation.models",
    )


def test_import_aggregation_engine_then_knowledge_models_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.aggregation.engine",
        "sales_call_agent.knowledge.models",
    )
