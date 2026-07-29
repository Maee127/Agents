"""Subprocess-isolated import-order checks for orchestration."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("sales_call_agent.orchestration.models", "sales_call_agent.persistence.keys"),
        ("sales_call_agent.orchestration.dependencies", "sales_call_agent.persistence.fake"),
        ("sales_call_agent.orchestration.engine", "sales_call_agent.evaluation.models"),
        ("sales_call_agent.persistence.fake", "sales_call_agent.orchestration.engine"),
    ],
)
def test_orchestration_import_orders_are_cycle_free(first: str, second: str) -> None:
    code = (
        f"import importlib; importlib.import_module({first!r}); importlib.import_module({second!r})"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
