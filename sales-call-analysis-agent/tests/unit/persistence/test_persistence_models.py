"""Unit tests for persistence keys and versioned wrappers."""

from __future__ import annotations

import subprocess
import sys

import pytest

from sales_call_agent.aggregation.models import AggregationConfig
from sales_call_agent.domain.models import Call
from sales_call_agent.persistence.exceptions import InvalidPersistenceInputError
from sales_call_agent.persistence.keys import (
    CallScoreKey,
    EvaluationKey,
    aggregation_policy_fingerprint,
    parse_semver_core,
)
from sales_call_agent.persistence.records import (
    VersionedCallRecord,
    VersionedKnowledgeSourceRecord,
    VersionedRubricRecord,
)


def test_semver_parse_strict() -> None:
    assert parse_semver_core("1.10.0") > parse_semver_core("1.9.0")
    with pytest.raises(InvalidPersistenceInputError):
        parse_semver_core("1.0")


def test_evaluation_key_sort_key() -> None:
    key = EvaluationKey(
        call_id="call-1",
        rubric_id="rubric_1",
        rubric_version="1.2.3",
        provider_name="provider",
        model_name="model",
    )
    assert key.sort_key == ("call-1", "rubric_1", (1, 2, 3), "provider", "model")


def test_call_score_key_sort_key() -> None:
    eval_key = EvaluationKey(
        call_id="call-1",
        rubric_id="rubric_1",
        rubric_version="1.2.3",
        provider_name="provider",
        model_name="model",
    )
    score_key = CallScoreKey(
        evaluation_key=eval_key,
        aggregation_policy_fingerprint="a" * 64,
    )
    assert score_key.sort_key[-1] == "a" * 64


def test_fingerprint_uses_float_hex_exactly() -> None:
    config = AggregationConfig(
        minimum_scored_weight_coverage=float.fromhex("0x1.0000000000001p-1"),
        minimum_scored_criterion_coverage=0.5,
        require_no_human_review_for_publish=True,
    )
    config_2 = AggregationConfig(
        minimum_scored_weight_coverage=0.5,
        minimum_scored_criterion_coverage=0.5,
        require_no_human_review_for_publish=True,
    )
    first = aggregation_policy_fingerprint(config)
    second = aggregation_policy_fingerprint(config_2)
    assert first != second
    assert len(first) == 64


def test_fingerprint_is_process_stable() -> None:
    code = (
        "from sales_call_agent.aggregation.models import AggregationConfig\n"
        "from sales_call_agent.persistence.keys import aggregation_policy_fingerprint\n"
        "cfg=AggregationConfig(minimum_scored_weight_coverage=0.7,"
        "minimum_scored_criterion_coverage=0.7,require_no_human_review_for_publish=False)\n"
        "print(aggregation_policy_fingerprint(cfg))\n"
    )
    run1 = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    run2 = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert run1.stdout.strip() == run2.stdout.strip()


def test_versioned_wrappers_validate_revision(
    call: object,
    knowledge_source: object,
    rubric: object,
) -> None:
    with pytest.raises(InvalidPersistenceInputError):
        VersionedCallRecord(value=call, revision=0)  # type: ignore[arg-type]
    with pytest.raises(InvalidPersistenceInputError):
        VersionedKnowledgeSourceRecord(value=knowledge_source, revision=True)  # type: ignore[arg-type]
    with pytest.raises(InvalidPersistenceInputError):
        VersionedRubricRecord(value=rubric, revision=0)


def test_call_aggregate_shape(call: Call) -> None:
    assert isinstance(call, Call)
    assert call.metadata is not None
    assert call.audio is not None
    assert call.status is not None
