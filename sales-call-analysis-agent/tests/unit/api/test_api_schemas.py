"""Unit tests for API schema strictness and validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sales_call_agent.api.schemas.calls import CallCreateRequest
from sales_call_agent.api.schemas.common import (
    validate_safe_identifier,
    validate_semver,
    validate_sha256_hex,
)
from sales_call_agent.api.schemas.pipeline import (
    PipelineRunRequest,
    RoleEvidenceRequest,
)
from sales_call_agent.api.schemas.rubrics import RubricRevisionSummary

_OPAQUE_REF = "opaque://audio/original/unit-test-example"
_OPAQUE_HASH = "a" * 64


def _minimal_call_request(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "call_id": "call-001",
        "seller_number": "seller-001",
        "source_type": "recorder_app",
        "call_timestamp": "2026-07-29T10:00:00+00:00",
        "duration_seconds": 4.0,
        "original_filename": "call.wav",
        "audio_channels": "mono",
        "original_audio_storage_ref": _OPAQUE_REF,
        "original_audio_content_hash": _OPAQUE_HASH,
    }
    base.update(overrides)
    return base


def test_call_create_request_accepts_valid_payload() -> None:
    req = CallCreateRequest.model_validate(_minimal_call_request())
    assert req.call_id == "call-001"


def test_call_create_request_storage_ref_is_secret() -> None:
    """storage_ref must not appear in repr or str of the request model."""
    req = CallCreateRequest.model_validate(_minimal_call_request())
    r = repr(req)
    assert _OPAQUE_REF not in r
    assert "**" in r or "SecretStr" in r


def test_call_create_request_rejects_unknown_field() -> None:
    payload = _minimal_call_request(unknown_field="value")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CallCreateRequest.model_validate(payload)


def test_call_create_request_rejects_invalid_call_id() -> None:
    with pytest.raises(ValidationError):
        CallCreateRequest.model_validate(_minimal_call_request(call_id="invalid/id"))


def test_call_create_request_requires_string_call_id() -> None:
    with pytest.raises(ValidationError):
        CallCreateRequest.model_validate(_minimal_call_request(call_id=123))


def test_pipeline_run_request_accepts_valid_payload() -> None:
    req = PipelineRunRequest.model_validate(
        {
            "call_id": "call-001",
            "target": "aggregation",
            "rubric_id": "rubric-001",
            "rubric_version": "1.0.0",
            "role_evidence": [],
            "normalized_audio": {
                "storage_ref": "opaque://audio/normalized/unit-test",
                "content_hash": "b" * 64,
                "duration_seconds": 4.0,
            },
        }
    )
    assert req.call_id == "call-001"
    assert req.normalized_audio is not None
    assert req.normalized_audio.content_hash == "b" * 64


def test_pipeline_run_request_normalized_audio_storage_ref_is_secret() -> None:
    opaque = "opaque://audio/normalized/unit-secret-test"
    req = PipelineRunRequest.model_validate(
        {
            "call_id": "call-001",
            "normalized_audio": {"storage_ref": opaque, "content_hash": "c" * 64},
        }
    )
    assert req.normalized_audio is not None
    r = repr(req.normalized_audio)
    assert opaque not in r


def test_pipeline_run_request_rejects_provider_name_field() -> None:
    """provider_name must not be accepted on pipeline requests."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PipelineRunRequest.model_validate(
            {"call_id": "call-001", "provider_name": "attacker_controlled"}
        )


def test_pipeline_run_request_rejects_model_name_field() -> None:
    """model_name must not be accepted on pipeline requests."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PipelineRunRequest.model_validate({"call_id": "call-001", "model_name": "override_model"})


def test_pipeline_run_request_optional_normalized_audio() -> None:
    req = PipelineRunRequest.model_validate({"call_id": "call-001"})
    assert req.normalized_audio is None


def test_pipeline_run_request_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        PipelineRunRequest.model_validate({"call_id": "call-001", "extra": True})


def test_role_evidence_request_requires_valid_evidence_id() -> None:
    with pytest.raises(ValidationError):
        RoleEvidenceRequest.model_validate(
            {
                "evidence_id": "bad/id",
                "speaker_label": "SPEAKER_00",
                "evidence_type": "operator_override",
                "suggested_role": "seller",
            }
        )


def test_rubric_revision_summary_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RubricRevisionSummary.model_validate(
            {
                "rubric_id": "rubric-001",
                "version": "1.0.0",
                "status": "approved",
                "revision": 1,
                "criterion_ids": [],
                "source_ids": [],
                "proprietary_text": "SHOULD_NOT_APPEAR",
            }
        )


def test_validate_safe_identifier_rejects_path_chars() -> None:
    with pytest.raises(ValueError):
        validate_safe_identifier("../traversal")


def test_validate_safe_identifier_accepts_valid() -> None:
    assert validate_safe_identifier("call-001") == "call-001"


def test_validate_semver_rejects_non_semver() -> None:
    with pytest.raises(ValueError):
        validate_semver("1.0")


def test_validate_semver_accepts_valid() -> None:
    assert validate_semver("1.2.3") == "1.2.3"


def test_validate_sha256_hex_rejects_short() -> None:
    with pytest.raises(ValueError):
        validate_sha256_hex("abc")


def test_validate_sha256_hex_accepts_valid() -> None:
    value = "a" * 64
    assert validate_sha256_hex(value) == value
