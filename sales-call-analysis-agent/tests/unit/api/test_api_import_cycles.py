"""Unit tests for API import cycle isolation."""

from __future__ import annotations

import subprocess
import sys


def _check_import(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Import of {module!r} failed:\n{result.stderr}"


def test_api_app_import_succeeds() -> None:
    _check_import("sales_call_agent.api.app")


def test_api_errors_import_succeeds() -> None:
    _check_import("sales_call_agent.api.errors")


def test_api_dependencies_import_succeeds() -> None:
    _check_import("sales_call_agent.api.dependencies")


def test_api_schemas_common_import_succeeds() -> None:
    _check_import("sales_call_agent.api.schemas.common")


def test_api_schemas_calls_import_succeeds() -> None:
    _check_import("sales_call_agent.api.schemas.calls")


def test_api_schemas_pipeline_import_succeeds() -> None:
    _check_import("sales_call_agent.api.schemas.pipeline")


def test_api_mappers_import_succeeds() -> None:
    _check_import("sales_call_agent.api.mappers")


def test_domain_not_importing_api() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sales_call_agent.domain.models; "
            "import sys; "
            "api_imports = [k for k in sys.modules if k.startswith('sales_call_agent.api')]; "
            "assert not api_imports, f'domain imported API: {api_imports}'",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_orchestration_not_importing_api() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sales_call_agent.orchestration.engine; "
            "import sys; "
            "api_imports = [k for k in sys.modules if 'sales_call_agent.api' in k]; "
            "assert not api_imports, f'orchestration imported API: {api_imports}'",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
