"""Regression tests for import-cycle safety across transcription/audio/ingestion."""

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


def test_import_transcription_then_ingestion_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.transcription.models",
        "sales_call_agent.ingestion.local_file",
    )


def test_import_ingestion_then_transcription_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.ingestion.local_file",
        "sales_call_agent.transcription.provider",
    )


def test_import_audio_normalize_then_transcription_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.audio.normalize",
        "sales_call_agent.transcription.fake",
    )


def test_import_faster_whisper_provider_then_ingestion_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.transcription.providers.faster_whisper",
        "sales_call_agent.ingestion.local_file",
    )


def test_import_ingestion_then_faster_whisper_provider_has_no_cycle() -> None:
    _import_in_order(
        "sales_call_agent.ingestion.local_file",
        "sales_call_agent.transcription.providers.faster_whisper",
    )


def test_import_cycle_check_does_not_replace_existing_ingestion_module() -> None:
    import sales_call_agent.ingestion.local_file as local_file_module

    original_module = local_file_module
    original_function = local_file_module.ingest_local_file
    original_globals = original_function.__globals__

    _import_in_order(
        "sales_call_agent.transcription.models",
        "sales_call_agent.ingestion.local_file",
    )

    current_module = sys.modules["sales_call_agent.ingestion.local_file"]
    assert current_module is original_module
    assert current_module.ingest_local_file is original_function
    assert original_function.__globals__ is current_module.__dict__
    assert original_globals is current_module.__dict__
