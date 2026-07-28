"""Unit tests for in-memory unit-of-work transaction behavior."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sales_call_agent.domain.models import CallProcessingStatus
from sales_call_agent.persistence.exceptions import RecordNotFoundError, StaleRecordVersionError
from sales_call_agent.persistence.fake import InMemoryPersistenceStore, InMemoryUnitOfWork


def test_precommit_reader_isolation_and_postcommit_visibility(call: object) -> None:
    store = InMemoryPersistenceStore()
    writer = InMemoryUnitOfWork(store=store)
    reader_before_commit = InMemoryUnitOfWork(store=store)

    writer.calls.add(call)  # type: ignore[arg-type]
    with pytest.raises(RecordNotFoundError):
        reader_before_commit.calls.get(call.call_id)  # type: ignore[attr-defined]

    writer.commit()

    reader_after_commit = InMemoryUnitOfWork(store=store)
    assert reader_after_commit.calls.get(call.call_id).value == call  # type: ignore[attr-defined]
    with pytest.raises(RecordNotFoundError):
        reader_before_commit.calls.get(call.call_id)  # type: ignore[attr-defined]


def test_stale_concurrent_commit_rejected(call: object) -> None:
    store = InMemoryPersistenceStore()
    first = InMemoryUnitOfWork(store=store)
    second = InMemoryUnitOfWork(store=store)

    first.calls.add(call)  # type: ignore[arg-type]
    first.commit()
    second.calls.add(replace(call, status=CallProcessingStatus.VALIDATED))  # type: ignore[arg-type]
    with pytest.raises(StaleRecordVersionError):
        second.commit()


def test_consecutive_commits_and_rollback_refresh(call: object) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    uow.calls.add(call)  # type: ignore[arg-type]
    uow.commit()

    validated = replace(call, status=CallProcessingStatus.VALIDATED)  # type: ignore[arg-type]
    uow.calls.update(validated, expected_revision=1)
    uow.commit()
    assert uow.calls.get(call.call_id).value.status is CallProcessingStatus.VALIDATED  # type: ignore[attr-defined]

    failed = replace(call, status=CallProcessingStatus.FAILED)  # type: ignore[arg-type]
    uow.calls.update(failed, expected_revision=2)
    uow.rollback()
    assert uow.calls.get(call.call_id).value.status is CallProcessingStatus.VALIDATED  # type: ignore[attr-defined]
