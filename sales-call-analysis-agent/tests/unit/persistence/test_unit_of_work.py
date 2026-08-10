"""Unit tests for in-memory unit-of-work transaction behavior."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sales_call_agent.domain.models import Call, CallProcessingStatus
from sales_call_agent.persistence.exceptions import RecordNotFoundError, StaleRecordVersionError
from sales_call_agent.persistence.fake import InMemoryPersistenceStore, InMemoryUnitOfWork


def test_precommit_reader_isolation_and_postcommit_visibility(call: Call) -> None:
    store = InMemoryPersistenceStore()
    writer = InMemoryUnitOfWork(store=store)
    reader_before_commit = InMemoryUnitOfWork(store=store)

    writer.calls.add(call)
    with pytest.raises(RecordNotFoundError):
        reader_before_commit.calls.get(call.call_id)

    writer.commit()

    reader_after_commit = InMemoryUnitOfWork(store=store)
    assert reader_after_commit.calls.get(call.call_id).value == call
    with pytest.raises(RecordNotFoundError):
        reader_before_commit.calls.get(call.call_id)


def test_stale_concurrent_commit_rejected(call: Call) -> None:
    store = InMemoryPersistenceStore()
    first = InMemoryUnitOfWork(store=store)
    second = InMemoryUnitOfWork(store=store)

    first.calls.add(call)
    first.commit()
    second.calls.add(replace(call, status=CallProcessingStatus.VALIDATED))
    with pytest.raises(StaleRecordVersionError):
        second.commit()


def test_consecutive_commits_and_rollback_refresh(call: Call) -> None:
    store = InMemoryPersistenceStore()
    uow = InMemoryUnitOfWork(store=store)
    uow.calls.add(call)
    uow.commit()

    validated = replace(call, status=CallProcessingStatus.VALIDATED)
    uow.calls.update(validated, expected_revision=1)
    uow.commit()
    assert uow.calls.get(call.call_id).value.status is CallProcessingStatus.VALIDATED

    failed = replace(call, status=CallProcessingStatus.FAILED)
    uow.calls.update(failed, expected_revision=2)
    uow.rollback()
    assert uow.calls.get(call.call_id).value.status is CallProcessingStatus.VALIDATED
