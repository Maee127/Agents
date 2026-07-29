"""Integration tests for POST/GET /api/v1/calls."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sales_call_agent.api.app import create_app
from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.evaluation.fake import DeterministicFakeEvaluationProvider
from sales_call_agent.orchestration.dependencies import (
    InMemoryUnitOfWorkFactory,
    PipelineDependencies,
)
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider

_OPAQUE_STORAGE_REF = "opaque://audio/original/example"
_OPAQUE_CONTENT_HASH = "a" * 64


def _make_client(store: InMemoryPersistenceStore | None = None) -> TestClient:
    if store is None:
        store = InMemoryPersistenceStore()
    uow_factory = InMemoryUnitOfWorkFactory(store=store)
    pipeline_deps = PipelineDependencies(
        transcription_provider=DeterministicFakeTranscriptionProvider(),
        diarization_provider=DeterministicFakeDiarizationProvider(),
        evaluation_provider=DeterministicFakeEvaluationProvider(),
        unit_of_work_factory=uow_factory,
    )
    deps = ApiDependencies(
        unit_of_work_factory=uow_factory,
        pipeline_dependencies=pipeline_deps,
    )
    return TestClient(create_app(deps), raise_server_exceptions=True)


def _call_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "call_id": "call-api-001",
        "seller_number": "SECRET_SELLER",
        "source_type": "recorder_app",
        "call_timestamp": "2026-07-29T10:00:00+00:00",
        "duration_seconds": 4.0,
        "original_filename": "SECRET_CALL.wav",
        "audio_channels": "mono",
        "original_audio_storage_ref": _OPAQUE_STORAGE_REF,
        "original_audio_content_hash": _OPAQUE_CONTENT_HASH,
    }
    base.update(overrides)
    return base


def test_create_call_returns_201() -> None:
    client = _make_client()
    resp = client.post("/api/v1/calls", json=_call_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["call_id"] == "call-api-001"
    assert body["status"] == "received"
    assert body["revision"] == 1


def test_create_call_response_omits_pii() -> None:
    client = _make_client()
    resp = client.post("/api/v1/calls", json=_call_payload())
    text = resp.text
    assert "SECRET_SELLER" not in text
    assert "SECRET_CALL" not in text
    assert _OPAQUE_STORAGE_REF not in text
    assert _OPAQUE_CONTENT_HASH not in text


def test_create_call_response_contains_expected_fields() -> None:
    client = _make_client()
    resp = client.post("/api/v1/calls", json=_call_payload())
    body = resp.json()
    assert set(body.keys()) == {
        "call_id",
        "status",
        "revision",
        "source_type",
        "audio_channels",
        "duration_seconds",
        "has_transcription",
        "has_diarization",
        "has_alignment",
        "has_role_assignment",
    }


def test_create_call_idempotent_duplicate_returns_200() -> None:
    client = _make_client()
    payload = _call_payload()
    resp1 = client.post("/api/v1/calls", json=payload)
    assert resp1.status_code == 201
    resp2 = client.post("/api/v1/calls", json=payload)
    assert resp2.status_code == 200
    assert resp1.json()["call_id"] == resp2.json()["call_id"]


def test_create_call_conflict_returns_409() -> None:
    client = _make_client()
    client.post("/api/v1/calls", json=_call_payload())
    different_hash = "b" * 64
    resp = client.post(
        "/api/v1/calls",
        json=_call_payload(original_audio_content_hash=different_hash),
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "resource_conflict"


def test_get_call_returns_200_after_create() -> None:
    client = _make_client()
    client.post("/api/v1/calls", json=_call_payload())
    resp = client.get("/api/v1/calls/call-api-001")
    assert resp.status_code == 200
    assert resp.json()["call_id"] == "call-api-001"


def test_get_call_not_found_returns_404() -> None:
    client = _make_client()
    resp = client.get("/api/v1/calls/call-does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "resource_not_found"


def test_get_call_shows_artifact_flags() -> None:
    client = _make_client()
    client.post("/api/v1/calls", json=_call_payload())
    resp = client.get("/api/v1/calls/call-api-001")
    body = resp.json()
    assert body["has_transcription"] is False
    assert body["has_diarization"] is False
    assert body["has_alignment"] is False
    assert body["has_role_assignment"] is False


def test_create_call_invalid_body_returns_422_with_stable_schema() -> None:
    client = _make_client()
    resp = client.post("/api/v1/calls", json={"call_id": 123})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "invalid_request"
    assert body["retryable"] is False
    assert "field_errors" in body


def test_validation_error_does_not_echo_input_value() -> None:
    """Pydantic validation error responses must not reflect back input data."""
    client = _make_client()
    secret_value = "SECRET_INPUT_VALUE"
    resp = client.post(
        "/api/v1/calls",
        json={"call_id": secret_value + "/bad/path"},
    )
    assert resp.status_code == 422
    assert secret_value not in resp.text


def test_create_call_app_isolation() -> None:
    """A call created in app_a must be absent in app_b (separate stores)."""
    store_a = InMemoryPersistenceStore()
    store_b = InMemoryPersistenceStore()
    client_a = _make_client(store_a)
    client_b = _make_client(store_b)

    resp = client_a.post("/api/v1/calls", json=_call_payload())
    assert resp.status_code == 201

    resp_b = client_b.get("/api/v1/calls/call-api-001")
    assert resp_b.status_code == 404
