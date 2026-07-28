"""Regression tests for import-cycle safety across evaluation packages."""

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


def test_import_evaluation_models_then_knowledge_has_no_cycle() -> None:
    _import_in_order("sales_call_agent.evaluation.models", "sales_call_agent.knowledge.models")


def test_import_evaluation_provider_then_alignment_has_no_cycle() -> None:
    _import_in_order("sales_call_agent.evaluation.provider", "sales_call_agent.alignment.models")


def test_import_evaluation_fake_then_speaker_identity_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.evaluation.fake",
        "sales_call_agent.speaker_identity.models",
    )
