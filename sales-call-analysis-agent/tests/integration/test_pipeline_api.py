"""Integration tests for POST /api/v1/pipeline-runs."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from sales_call_agent.api.app import create_app
from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
from sales_call_agent.domain.models import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    SourceType,
)
from sales_call_agent.evaluation.fake import DeterministicFakeEvaluationProvider
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    RubricCriterion,
    RubricCriterionCategory,
    RubricScoreLevel,
    RubricScoringScale,
    RubricStatus,
    SalesRubric,
)
from sales_call_agent.orchestration.dependencies import (
    InMemoryUnitOfWorkFactory,
    PipelineDependencies,
)
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider

_OPAQUE_ORIGINAL = "opaque://audio/original/pipeline-example"
_OPAQUE_NORMALIZED = "opaque://audio/normalized/pipeline-example"


def _rubric() -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale-api-001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="no"),
            RubricScoreLevel(score=1.0, label="yes", description="yes"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric-api-001",
        name="API integration rubric",
        version="1.0.0",
        description="Synthetic.",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion-api-001",
                name="Discovery",
                definition="Question asked.",
                positive_guidance="Ask.",
                negative_guidance="Do not pitch.",
                category=RubricCriterionCategory.DISCOVERY,
                origin=CriterionOrigin.ORGANIZATION_DEFINED,
                weight=1.0,
                scoring_scale=scale,
                evidence_requirement=EvidenceRequirement(),
            ),
        ),
    )


def _call() -> Call:
    path = _OPAQUE_ORIGINAL
    return Call(
        metadata=CallMetadata(
            call_id="call-pipeline-001",
            seller_number="SECRET_SELLER",
            source_type=SourceType.RECORDER_APP,
            call_timestamp=datetime(2026, 7, 29, tzinfo=UTC),
            duration_seconds=4.0,
            counterparty_phone="SECRET_CUSTOMER",
            original_filename="SECRET_PIPELINE.wav",
            audio_channels=AudioChannels.MONO,
            storage_path=path,
        ),
        audio=AudioAsset(
            storage_path=path, audio_channels=AudioChannels.MONO, content_hash="original"
        ),
        status=CallProcessingStatus.VALIDATED,
    )


def _setup(store: InMemoryPersistenceStore) -> None:
    uow_factory = InMemoryUnitOfWorkFactory(store=store)
    uow = uow_factory()
    uow.calls.add(_call())
    rubric = _rubric()
    uow.rubrics.add(replace(rubric, status=RubricStatus.DRAFT))
    uow.rubrics.update_status(
        rubric.rubric_id, rubric.version, status=RubricStatus.APPROVED, expected_revision=1
    )
    uow.commit()


def _make_client(store: InMemoryPersistenceStore) -> TestClient:
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


def _pipeline_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "call_id": "call-pipeline-001",
        "target": "aggregation",
        "rubric_id": "rubric-api-001",
        "rubric_version": "1.0.0",
        "role_evidence": [
            {
                "evidence_id": "evidence-api-seller",
                "speaker_label": "SPEAKER_00",
                "evidence_type": "voice_identity_match",
                "suggested_role": "seller",
            }
        ],
        "normalized_audio": {
            "storage_ref": _OPAQUE_NORMALIZED,
            "content_hash": "b" * 64,
            "duration_seconds": 4.0,
        },
    }
    base.update(overrides)
    return base


def test_pipeline_run_succeeds() -> None:
    store = InMemoryPersistenceStore()
    _setup(store)
    client = _make_client(store)
    resp = client.post("/api/v1/pipeline-runs", json=_pipeline_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["call_id"] == "call-pipeline-001"
    assert body["reached_stage"] == "aggregation"
    assert body["evaluation_key"] is not None
    assert body["call_score_key"] is not None


def test_pipeline_run_response_omits_storage_ref() -> None:
    store = InMemoryPersistenceStore()
    _setup(store)
    client = _make_client(store)
    resp = client.post("/api/v1/pipeline-runs", json=_pipeline_payload())
    text = resp.text
    assert _OPAQUE_NORMALIZED not in text
    assert _OPAQUE_ORIGINAL not in text
    assert "SECRET_SELLER" not in text
    assert "SECRET_CUSTOMER" not in text


def test_pipeline_run_does_not_accept_provider_or_model_fields() -> None:
    """Pipeline request must not expose provider/model override fields."""
    store = InMemoryPersistenceStore()
    _setup(store)
    client = _make_client(store)
    payload = _pipeline_payload()
    payload["provider_name"] = "attacker_controlled"  # type: ignore[assignment]
    resp = client.post("/api/v1/pipeline-runs", json=payload)
    assert resp.status_code == 422


def test_pipeline_run_second_call_reuses_results() -> None:
    store = InMemoryPersistenceStore()
    _setup(store)
    client = _make_client(store)
    payload_with_audio = _pipeline_payload()
    payload_without_audio: dict[str, object] = {
        "call_id": "call-pipeline-001",
        "target": "aggregation",
        "rubric_id": "rubric-api-001",
        "rubric_version": "1.0.0",
        "role_evidence": [],
        "normalized_audio": None,
    }

    client.post("/api/v1/pipeline-runs", json=payload_with_audio)
    resp2 = client.post("/api/v1/pipeline-runs", json=payload_without_audio)
    assert resp2.status_code == 200
    body = resp2.json()
    stage_statuses = {o["stage"]: o["status"] for o in body["stage_outcomes"]}
    assert all(s == "reused" for s in stage_statuses.values())


def test_pipeline_run_app_isolation() -> None:
    """A pipeline run in app_a must not affect a separate app_b's store."""
    store_a = InMemoryPersistenceStore()
    store_b = InMemoryPersistenceStore()
    _setup(store_a)
    _setup(store_b)
    client_a = _make_client(store_a)
    client_b = _make_client(store_b)

    resp_a = client_a.post("/api/v1/pipeline-runs", json=_pipeline_payload())
    assert resp_a.status_code == 200

    # store_b seeded separately; both succeed but results are independent
    resp_b = client_b.post("/api/v1/pipeline-runs", json=_pipeline_payload())
    assert resp_b.status_code == 200

    # A call NOT in store_b returns an error there
    payload_missing = _pipeline_payload(call_id="call-missing")
    resp_missing = client_b.post("/api/v1/pipeline-runs", json=payload_missing)
    assert resp_missing.status_code != 200
