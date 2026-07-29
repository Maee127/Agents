"""Integration tests for rubric revision read endpoints."""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from sales_call_agent.api.app import create_app
from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.diarization.fake import DeterministicFakeDiarizationProvider
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


def _rubric(version: str = "1.0.0") -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale-rubric-api-001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="no"),
            RubricScoreLevel(score=1.0, label="yes", description="yes"),
        ),
    )
    return SalesRubric(
        rubric_id="rubric-read-001",
        name="Read rubric",
        version=version,
        description="Synthetic.",
        status=RubricStatus.APPROVED,
        criteria=(
            RubricCriterion(
                criterion_id="criterion-read-001",
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


def _seed_rubric(store: InMemoryPersistenceStore, rubric: SalesRubric) -> None:
    uow = InMemoryUnitOfWorkFactory(store=store)()
    uow.rubrics.add(replace(rubric, status=RubricStatus.DRAFT))
    uow.rubrics.update_status(
        rubric.rubric_id, rubric.version, status=RubricStatus.APPROVED, expected_revision=1
    )
    uow.commit()


def test_get_rubric_revision_returns_summary() -> None:
    store = InMemoryPersistenceStore()
    _seed_rubric(store, _rubric())
    client = _make_client(store)
    resp = client.get("/api/v1/rubrics/rubric-read-001/1.0.0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rubric_id"] == "rubric-read-001"
    assert body["version"] == "1.0.0"
    assert "criterion-read-001" in body["criterion_ids"]


def test_rubric_response_contains_only_summary_fields() -> None:
    store = InMemoryPersistenceStore()
    _seed_rubric(store, _rubric())
    client = _make_client(store)
    resp = client.get("/api/v1/rubrics/rubric-read-001/1.0.0")
    body = resp.json()
    allowed = {
        "rubric_id",
        "version",
        "status",
        "revision",
        "criterion_ids",
        "source_ids",
        "language",
    }
    assert set(body.keys()) == allowed


def test_get_rubric_revision_omits_proprietary_content() -> None:
    store = InMemoryPersistenceStore()
    _seed_rubric(store, _rubric())
    client = _make_client(store)
    resp = client.get("/api/v1/rubrics/rubric-read-001/1.0.0")
    body_text = resp.text
    assert "Question asked." not in body_text
    assert "Ask." not in body_text
    assert "Do not pitch." not in body_text


def test_list_rubric_revisions_returns_all_versions() -> None:
    store = InMemoryPersistenceStore()
    _seed_rubric(store, _rubric("1.0.0"))
    _seed_rubric(store, _rubric("2.0.0"))
    client = _make_client(store)
    resp = client.get("/api/v1/rubrics/rubric-read-001")
    assert resp.status_code == 200
    body = resp.json()
    versions = [r["version"] for r in body["revisions"]]
    assert "1.0.0" in versions
    assert "2.0.0" in versions


def test_get_rubric_revision_not_found_returns_404() -> None:
    store = InMemoryPersistenceStore()
    client = _make_client(store)
    resp = client.get("/api/v1/rubrics/rubric-does-not-exist/1.0.0")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "resource_not_found"
