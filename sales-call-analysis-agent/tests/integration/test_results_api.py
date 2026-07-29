"""Integration tests for exact-key evaluation and call-score retrieval endpoints."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

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
from sales_call_agent.orchestration.engine import run_call_pipeline
from sales_call_agent.orchestration.models import NormalizedAudioReference, RunCallPipelineRequest
from sales_call_agent.persistence.fake import InMemoryPersistenceStore
from sales_call_agent.speaker_identity.models import (
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)
from sales_call_agent.transcription.fake import DeterministicFakeTranscriptionProvider

_OPAQUE_ORIGINAL = "opaque://audio/original/results-example"
_OPAQUE_NORMALIZED = "opaque://audio/normalized/results-example"


def _rubric() -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale-results-001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="no"),
            RubricScoreLevel(score=1.0, label="yes", description="yes"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric-results-001",
        name="Results test rubric",
        version="1.0.0",
        description="Synthetic.",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion-results-001",
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
    return Call(
        metadata=CallMetadata(
            call_id="call-results-001",
            seller_number="SECRET_SELLER",
            source_type=SourceType.RECORDER_APP,
            call_timestamp=datetime(2026, 7, 29, tzinfo=UTC),
            duration_seconds=4.0,
            counterparty_phone="SECRET_CUSTOMER",
            original_filename="SECRET_RESULTS.wav",
            audio_channels=AudioChannels.MONO,
            storage_path=_OPAQUE_ORIGINAL,
        ),
        audio=AudioAsset(
            storage_path=_OPAQUE_ORIGINAL,
            audio_channels=AudioChannels.MONO,
            content_hash="original-res",
        ),
        status=CallProcessingStatus.VALIDATED,
    )


def _make_client_and_store() -> tuple[TestClient, InMemoryPersistenceStore, PipelineDependencies]:
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
    return TestClient(create_app(deps), raise_server_exceptions=True), store, pipeline_deps


def _seed_and_run(store: InMemoryPersistenceStore, pipeline_deps: PipelineDependencies) -> None:
    uow_factory = InMemoryUnitOfWorkFactory(store=store)
    uow = uow_factory()
    rubric = _rubric()
    uow.calls.add(_call())
    uow.rubrics.add(replace(rubric, status=RubricStatus.DRAFT))
    uow.rubrics.update_status(
        rubric.rubric_id, rubric.version, status=RubricStatus.APPROVED, expected_revision=1
    )
    uow.commit()
    audio = NormalizedAudioReference(
        storage_path=Path(_OPAQUE_NORMALIZED),
        content_hash="normalized-results",
        duration_seconds=4.0,
    )
    req = RunCallPipelineRequest(
        call_id="call-results-001",
        rubric_id="rubric-results-001",
        rubric_version="1.0.0",
        role_evidence=(
            RoleEvidence(
                evidence_id="evidence-results-seller",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.VOICE_IDENTITY_MATCH,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
        normalized_audio=audio,
    )
    run_call_pipeline(req, pipeline_deps)


def test_get_evaluation_returns_result() -> None:
    client, store, pipeline_deps = _make_client_and_store()
    _seed_and_run(store, pipeline_deps)
    resp = client.get(
        "/api/v1/evaluations",
        params={
            "call_id": "call-results-001",
            "rubric_id": "rubric-results-001",
            "rubric_version": "1.0.0",
            "provider_name": "fake_evaluator",
            "model_name": "fake_eval_v1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["call_id"] == "call-results-001"
    assert body["rubric_id"] == "rubric-results-001"


def test_get_evaluation_omits_sensitive_data() -> None:
    client, store, pipeline_deps = _make_client_and_store()
    _seed_and_run(store, pipeline_deps)
    resp = client.get(
        "/api/v1/evaluations",
        params={
            "call_id": "call-results-001",
            "rubric_id": "rubric-results-001",
            "rubric_version": "1.0.0",
            "provider_name": "fake_evaluator",
            "model_name": "fake_eval_v1",
        },
    )
    text = resp.text
    assert "SECRET_SELLER" not in text
    assert "SECRET_CUSTOMER" not in text
    assert "SECRET_RESULTS" not in text
    assert _OPAQUE_ORIGINAL not in text
    assert _OPAQUE_NORMALIZED not in text


def test_get_evaluation_not_found_returns_404() -> None:
    client, _store, _pipeline_deps = _make_client_and_store()
    resp = client.get(
        "/api/v1/evaluations",
        params={
            "call_id": "missing-call",
            "rubric_id": "rubric-results-001",
            "rubric_version": "1.0.0",
            "provider_name": "fake_evaluator",
            "model_name": "fake_eval_v1",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "resource_not_found"


def test_per_call_evaluation_list_endpoint_does_not_exist() -> None:
    """Broad per-call evaluation list is intentionally absent in v1."""
    client, store, pipeline_deps = _make_client_and_store()
    _seed_and_run(store, pipeline_deps)
    resp = client.get("/api/v1/calls/call-results-001/evaluations")
    assert resp.status_code == 404


def test_get_call_score_returns_result() -> None:
    client, store, pipeline_deps = _make_client_and_store()
    _seed_and_run(store, pipeline_deps)
    # Run pipeline via API to get the fingerprint from the response
    pipeline_resp = client.post(
        "/api/v1/pipeline-runs",
        json={
            "call_id": "call-results-001",
            "target": "aggregation",
            "rubric_id": "rubric-results-001",
            "rubric_version": "1.0.0",
            "role_evidence": [
                {
                    "evidence_id": "evidence-results-seller",
                    "speaker_label": "SPEAKER_00",
                    "evidence_type": "voice_identity_match",
                    "suggested_role": "seller",
                }
            ],
        },
    )
    assert pipeline_resp.status_code == 200
    call_score_key = pipeline_resp.json()["call_score_key"]
    fingerprint = call_score_key["aggregation_policy_fingerprint"]

    resp = client.get(
        "/api/v1/call-scores",
        params={
            "call_id": "call-results-001",
            "rubric_id": "rubric-results-001",
            "rubric_version": "1.0.0",
            "provider_name": "fake_evaluator",
            "model_name": "fake_eval_v1",
            "aggregation_policy_fingerprint": fingerprint,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["call_id"] == "call-results-001"
    assert body["publication_status"] in {
        "publishable",
        "limited_coverage",
        "human_review_required",
        "no_scorable_criteria",
    }


def test_per_call_score_list_endpoint_does_not_exist() -> None:
    """Broad per-call score list is intentionally absent in v1."""
    client, store, pipeline_deps = _make_client_and_store()
    _seed_and_run(store, pipeline_deps)
    resp = client.get("/api/v1/calls/call-results-001/call-scores")
    assert resp.status_code == 404


def test_openapi_schema_has_no_sensitive_values() -> None:
    """OpenAPI schema must not embed seeded secrets or real-looking examples."""
    client, _store, _pipeline_deps = _make_client_and_store()
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    text = resp.text
    sensitive = [
        "SECRET_TRANSCRIPT",
        "SECRET_RUBRIC",
        "SECRET_SOURCE",
        "SECRET_SELLER",
        "SECRET_CUSTOMER",
        "SECRET_RESULTS",
        _OPAQUE_ORIGINAL,
        _OPAQUE_NORMALIZED,
    ]
    for value in sensitive:
        assert value not in text, f"OpenAPI schema contains sensitive value: {value!r}"
