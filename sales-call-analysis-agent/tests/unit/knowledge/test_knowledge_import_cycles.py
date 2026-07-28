"""Regression tests for import-cycle safety across knowledge packages."""

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


def test_import_knowledge_models_then_alignment_has_no_cycle() -> None:
    _import_in_order("sales_call_agent.knowledge.models", "sales_call_agent.alignment.models")


def test_import_knowledge_rubric_then_speaker_identity_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.knowledge.rubric",
        "sales_call_agent.speaker_identity.models",
    )


def test_import_alignment_then_knowledge_rubric_has_no_cycle() -> None:
    _import_in_order("sales_call_agent.alignment.models", "sales_call_agent.knowledge.rubric")
