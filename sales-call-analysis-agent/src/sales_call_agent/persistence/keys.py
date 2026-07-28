"""Deterministic persistence keys and policy fingerprint helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from sales_call_agent.aggregation.models import AggregationConfig
from sales_call_agent.persistence.exceptions import InvalidPersistenceInputError

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SEMVER_CORE_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _ensure_required_string(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise InvalidPersistenceInputError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise InvalidPersistenceInputError(f"{field_name} must be non-empty and trimmed")


def _ensure_safe_identifier(value: object, field_name: str) -> None:
    _ensure_required_string(value, field_name)
    assert isinstance(value, str)
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise InvalidPersistenceInputError(f"{field_name} must be a safe identifier")
    if "/" in value or "\\" in value or ":" in value:
        raise InvalidPersistenceInputError(f"{field_name} must not contain path-like characters")


def _ensure_semver(value: object, field_name: str) -> None:
    _ensure_required_string(value, field_name)
    assert isinstance(value, str)
    if not _SEMVER_CORE_RE.fullmatch(value):
        raise InvalidPersistenceInputError(f"{field_name} must match MAJOR.MINOR.PATCH")


def parse_semver_core(version: str) -> tuple[int, int, int]:
    """Parse strict MAJOR.MINOR.PATCH SemVer core into a sort tuple."""
    _ensure_semver(version, "version")
    major_text, minor_text, patch_text = version.split(".")
    return (int(major_text), int(minor_text), int(patch_text))


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationKey:
    """Stable identity of one persisted evaluation record."""

    call_id: str
    rubric_id: str
    rubric_version: str
    provider_name: str
    model_name: str

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.call_id, "call_id")
        _ensure_safe_identifier(self.rubric_id, "rubric_id")
        _ensure_semver(self.rubric_version, "rubric_version")
        _ensure_safe_identifier(self.provider_name, "provider_name")
        _ensure_safe_identifier(self.model_name, "model_name")

    @property
    def sort_key(self) -> tuple[str, str, tuple[int, int, int], str, str]:
        """Deterministic ordering key for list operations."""
        return (
            self.call_id,
            self.rubric_id,
            parse_semver_core(self.rubric_version),
            self.provider_name,
            self.model_name,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CallScoreKey:
    """Stable identity of one persisted call-score record."""

    evaluation_key: EvaluationKey
    aggregation_policy_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation_key, EvaluationKey):
            raise InvalidPersistenceInputError("evaluation_key must be an EvaluationKey")
        _ensure_required_string(
            self.aggregation_policy_fingerprint,
            "aggregation_policy_fingerprint",
        )
        if not _FINGERPRINT_RE.fullmatch(self.aggregation_policy_fingerprint):
            raise InvalidPersistenceInputError(
                "aggregation_policy_fingerprint must be a lowercase SHA-256 hex string"
            )

    @property
    def sort_key(self) -> tuple[str, str, tuple[int, int, int], str, str, str]:
        """Deterministic ordering key for list operations."""
        return (*self.evaluation_key.sort_key, self.aggregation_policy_fingerprint)


def aggregation_policy_fingerprint(config: AggregationConfig) -> str:
    """Return deterministic SHA-256 fingerprint for one aggregation policy."""
    if not isinstance(config, AggregationConfig):
        raise InvalidPersistenceInputError("config must be an AggregationConfig")
    payload = {
        "minimum_scored_weight_coverage": config.minimum_scored_weight_coverage.hex(),
        "minimum_scored_criterion_coverage": config.minimum_scored_criterion_coverage.hex(),
        "require_no_human_review_for_publish": config.require_no_human_review_for_publish,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
