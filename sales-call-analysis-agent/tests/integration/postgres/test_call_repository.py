"""Integration tests for the PostgreSQL call repository."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from sales_call_agent.domain.models import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    SourceType,
)
from sales_call_agent.infrastructure.postgres.tables import calls
from sales_call_agent.persistence.exceptions import (
    InvalidPersistenceInputError,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    StaleRecordVersionError,
)
from sales_call_agent.persistence.repositories import CallRepository

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest.fixture(scope="module")
def postgres_schema() -> Iterator[tuple[Engine, str]]:
    database_url = os.environ.get("POSTGRES_TEST_URL")
    if database_url is None:
        pytest.fail("POSTGRES_TEST_URL must be set for PostgreSQL integration tests")

    engine = create_engine(database_url, echo=False, future=True)
    schema_name = f"test_call_repository_{uuid4().hex}"

    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema_name))
            translated_connection = connection.execution_options(
                schema_translate_map={None: schema_name}
            )
            calls.create(translated_connection)

        yield engine, schema_name
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema_name, cascade=True, if_exists=True))
        engine.dispose()


@pytest.fixture
def repository_context(
    postgres_schema: tuple[Engine, str],
) -> Iterator[tuple[CallRepository, Connection, Any]]:
    engine, schema_name = postgres_schema
    connection = engine.connect().execution_options(schema_translate_map={None: schema_name})
    transaction = connection.begin()

    # Imported lazily so the default-skipped suite can collect before the
    # production repository module exists.
    from sales_call_agent.infrastructure.postgres.call_repository import (
        PostgresCallRepository,
    )

    repository: CallRepository = PostgresCallRepository(connection)

    try:
        yield repository, connection, transaction
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def call() -> Call:
    metadata = CallMetadata(
        call_id="call-abc123def4567890",
        seller_number="SECRET_SELLER_NUMBER",
        source_type=SourceType.RECORDER_APP,
        call_timestamp=datetime(2026, 7, 28, tzinfo=UTC),
        duration_seconds=30.0,
        counterparty_phone="SECRET_COUNTERPARTY_PHONE",
        original_filename="SECRET_ORIGINAL_FILENAME.mp3",
        audio_channels=AudioChannels.MONO,
        storage_path=r"C:\SECRET\AUDIO.mp3",
    )
    audio = AudioAsset(
        storage_path=r"C:\SECRET\AUDIO.mp3",
        audio_channels=AudioChannels.MONO,
        content_hash="a" * 64,
    )
    return Call(
        metadata=metadata,
        audio=audio,
        status=CallProcessingStatus.RECEIVED,
    )


def _changed_call(call: Call) -> Call:
    changed_status = next(status for status in CallProcessingStatus if status != call.status)
    return replace(call, status=changed_status)


def _call_with_id(call: Call, call_id: str) -> Call:
    return replace(
        call,
        metadata=replace(call.metadata, call_id=call_id),
    )


def test_add_creates_revision_one_and_round_trips_all_fields(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context

    added = repository.add(call)
    fetched = repository.get(call.call_id)

    assert added.revision == 1
    assert added.value == call
    assert fetched == added
    assert fetched.value.metadata == call.metadata
    assert fetched.value.audio == call.audio
    assert fetched.value.status == call.status


def test_identical_duplicate_add_is_idempotent(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context

    first = repository.add(call)
    second = repository.add(call)

    assert second == first
    assert second.revision == 1


def test_conflicting_duplicate_add_raises_record_already_exists(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context
    repository.add(call)

    with pytest.raises(RecordAlreadyExistsError):
        repository.add(_changed_call(call))


def test_get_missing_raises_record_not_found(
    repository_context: tuple[CallRepository, Connection, Any],
) -> None:
    repository, _, _ = repository_context

    with pytest.raises(RecordNotFoundError):
        repository.get("call-missing")


def test_find_missing_returns_none(
    repository_context: tuple[CallRepository, Connection, Any],
) -> None:
    repository, _, _ = repository_context

    assert repository.find("call-missing") is None


def test_exists_returns_false_then_true(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context

    assert repository.exists(call.call_id) is False

    repository.add(call)

    assert repository.exists(call.call_id) is True


@pytest.mark.parametrize(
    "method_name",
    ("get", "find", "exists"),
)
@pytest.mark.parametrize(
    "invalid_identifier",
    ("", " call-id", "call-id ", "call/id", r"call\id", "call:id", 123),
)
def test_lookup_methods_reject_invalid_identifiers(
    repository_context: tuple[CallRepository, Connection, Any],
    method_name: str,
    invalid_identifier: object,
) -> None:
    repository, _, _ = repository_context
    method = cast(Any, getattr(repository, method_name))

    with pytest.raises(InvalidPersistenceInputError):
        method(invalid_identifier)


def test_unchanged_update_is_no_op(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context
    repository.add(call)

    updated = repository.update(call, expected_revision=1)

    assert updated.value == call
    assert updated.revision == 1


def test_changed_update_increments_revision_once(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context
    repository.add(call)
    changed_call = _changed_call(call)

    updated = repository.update(changed_call, expected_revision=1)

    assert updated.value == changed_call
    assert updated.revision == 2
    assert repository.get(call.call_id) == updated


def test_stale_update_raises_stale_record_version(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context
    repository.add(call)

    with pytest.raises(StaleRecordVersionError):
        repository.update(_changed_call(call), expected_revision=2)


def test_update_missing_raises_record_not_found(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context
    missing_call = _call_with_id(call, "call-missing")

    with pytest.raises(RecordNotFoundError):
        repository.update(missing_call, expected_revision=1)


def test_list_calls_returns_records_sorted_by_call_id(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, _ = repository_context
    repository.add(_call_with_id(call, "call-z"))
    repository.add(_call_with_id(call, "call-a"))
    repository.add(_call_with_id(call, "call-m"))

    records = repository.list_calls()

    assert tuple(record.value.call_id for record in records) == (
        "call-a",
        "call-m",
        "call-z",
    )


def test_repository_operations_do_not_commit_surrounding_transaction(
    repository_context: tuple[CallRepository, Connection, Any],
    call: Call,
) -> None:
    repository, _, transaction = repository_context

    repository.add(call)
    repository.update(_changed_call(call), expected_revision=1)

    assert transaction.is_active
