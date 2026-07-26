"""Regression tests for import-cycle safety across transcription/audio/ingestion."""

from __future__ import annotations

import importlib
import sys


def _clear_sales_call_agent_modules() -> None:
    keys = [
        key
        for key in sys.modules
        if key == "sales_call_agent" or key.startswith("sales_call_agent.")
    ]
    for key in keys:
        sys.modules.pop(key, None)


def _import_in_order(first: str, second: str) -> None:
    _clear_sales_call_agent_modules()
    importlib.import_module(first)
    importlib.import_module(second)


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
