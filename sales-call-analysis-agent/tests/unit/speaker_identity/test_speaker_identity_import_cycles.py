"""Regression tests for import-cycle safety across speaker-identity packages."""

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


def test_import_speaker_identity_then_ingestion_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.speaker_identity.models",
        "sales_call_agent.ingestion.local_file",
    )


def test_import_alignment_then_speaker_identity_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.alignment.engine",
        "sales_call_agent.speaker_identity.engine",
    )


def test_import_speaker_identity_does_not_import_api() -> None:
    code = (
        "import importlib, sys; "
        "importlib.import_module('sales_call_agent.speaker_identity.models'); "
        "loaded=[name for name in sys.modules if name.startswith('sales_call_agent.api')]; "
        "raise SystemExit(0 if loaded==[] else 1)"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
