"""Regression tests for import-cycle safety between audio and ingestion modules."""

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


def test_import_ingestion_then_normalize_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.ingestion.local_file",
        "sales_call_agent.audio.normalize",
    )


def test_import_normalize_then_ingestion_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.audio.normalize",
        "sales_call_agent.ingestion.local_file",
    )
