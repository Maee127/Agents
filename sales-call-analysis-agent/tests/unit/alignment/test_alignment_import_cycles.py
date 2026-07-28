"""Regression tests for import-cycle safety across alignment packages."""

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


def test_import_alignment_models_then_engine_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.alignment.models",
        "sales_call_agent.alignment.engine",
    )


def test_import_alignment_engine_then_transcription_models_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.alignment.engine",
        "sales_call_agent.transcription.models",
    )


def test_import_alignment_engine_then_diarization_models_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.alignment.engine",
        "sales_call_agent.diarization.models",
    )


def test_import_audio_normalize_then_alignment_engine_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.audio.normalize",
        "sales_call_agent.alignment.engine",
    )
