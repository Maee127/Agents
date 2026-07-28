"""Subprocess-isolated import-cycle checks for persistence contracts."""

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


def test_import_persistence_models_and_evaluation_models() -> None:
    _import_in_order("sales_call_agent.persistence.records", "sales_call_agent.evaluation.models")


def test_import_persistence_repositories_and_aggregation_models() -> None:
    _import_in_order(
        "sales_call_agent.persistence.repositories",
        "sales_call_agent.aggregation.models",
    )


def test_import_persistence_fake_and_domain_models() -> None:
    _import_in_order("sales_call_agent.persistence.fake", "sales_call_agent.domain.models")
