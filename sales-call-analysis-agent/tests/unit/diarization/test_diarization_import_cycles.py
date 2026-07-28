"""Regression tests for import-cycle safety across diarization packages."""

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


def test_import_diarization_then_ingestion_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.diarization.models",
        "sales_call_agent.ingestion.local_file",
    )


def test_import_ingestion_then_diarization_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.ingestion.local_file",
        "sales_call_agent.diarization.provider",
    )


def test_import_audio_normalize_then_diarization_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.audio.normalize",
        "sales_call_agent.diarization.fake",
    )


def test_import_diarization_does_not_import_transcription() -> None:
    code = (
        "import importlib, sys; "
        "importlib.import_module('sales_call_agent.diarization.models'); "
        "loaded=[name for name in sys.modules "
        "if name.startswith('sales_call_agent.transcription')]; "
        "raise SystemExit(0 if loaded==[] else 1)"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
