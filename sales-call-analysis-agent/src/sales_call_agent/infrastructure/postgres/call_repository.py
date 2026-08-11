"""PostgreSQL implementation of the call repository."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Connection, RowMapping, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import SQLAlchemyError

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
    RepositoryUnavailableError,
    StaleRecordVersionError,
)
from sales_call_agent.persistence.records import VersionedCallRecord
from sales_call_agent.persistence.repositories import CallRepository

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _ensure_safe_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidPersistenceInputError(f"{field_name} must be a string")
    if _SAFE_IDENTIFIER_RE.fullmatch(value) is None:
        raise InvalidPersistenceInputError(f"{field_name} has an invalid format")
    return value


def _ensure_call(value: object) -> Call:
    if not isinstance(value, Call):
        raise InvalidPersistenceInputError("call must be a Call")
    _ensure_safe_identifier(value.call_id, "call_id")
    return value


def _ensure_expected_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidPersistenceInputError("expected_revision must be an integer")
    return value


def _call_values(call: Call) -> dict[str, Any]:
    return {
        "call_id": call.call_id,
        "status": call.status.value,
        "source_type": call.metadata.source_type.value,
        "audio_channels": call.metadata.audio_channels.value,
        "call_timestamp": call.metadata.call_timestamp,
        "duration_seconds": call.metadata.duration_seconds,
        "seller_number": call.metadata.seller_number,
        "counterparty_phone": call.metadata.counterparty_phone,
        "original_filename": call.metadata.original_filename,
        "storage_path": call.metadata.storage_path,
        "content_hash": call.audio.content_hash,
    }


def _record_from_row(row: RowMapping) -> VersionedCallRecord:
    audio_channels = AudioChannels(row["audio_channels"])
    storage_path = row["storage_path"]

    metadata = CallMetadata(
        call_id=row["call_id"],
        seller_number=row["seller_number"],
        source_type=SourceType(row["source_type"]),
        call_timestamp=row["call_timestamp"],
        duration_seconds=row["duration_seconds"],
        counterparty_phone=row["counterparty_phone"],
        original_filename=row["original_filename"],
        audio_channels=audio_channels,
        storage_path=storage_path,
    )
    audio = AudioAsset(
        storage_path=storage_path,
        audio_channels=audio_channels,
        content_hash=row["content_hash"],
    )
    call = Call(
        metadata=metadata,
        audio=audio,
        status=CallProcessingStatus(row["status"]),
    )
    return VersionedCallRecord(
        value=call,
        revision=row["revision"],
    )


class PostgresCallRepository(CallRepository):
    """Persist call aggregates through an existing SQLAlchemy transaction."""

    def __init__(self, connection: Connection) -> None:
        if not isinstance(connection, Connection):
            raise InvalidPersistenceInputError("connection must be a SQLAlchemy Connection")
        self._connection = connection

    def add(self, call: Call) -> VersionedCallRecord:
        safe_call = _ensure_call(call)
        values = _call_values(safe_call)

        statement = (
            postgres_insert(calls)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[calls.c.call_id])
            .returning(*calls.c)
        )

        try:
            inserted = self._connection.execute(statement).mappings().first()
            if inserted is not None:
                return _record_from_row(inserted)

            existing = self._find_row(safe_call.call_id)
        except SQLAlchemyError as error:
            raise RepositoryUnavailableError(
                "call repository unavailable for add operation"
            ) from error

        if existing is None:
            raise RepositoryUnavailableError("call repository could not resolve conflicting add")

        record = _record_from_row(existing)
        if record.value != safe_call:
            raise RecordAlreadyExistsError("call record already exists")
        return record

    def get(self, call_id: str) -> VersionedCallRecord:
        safe_id = _ensure_safe_identifier(call_id, "call_id")

        try:
            row = self._find_row(safe_id)
        except SQLAlchemyError as error:
            raise RepositoryUnavailableError(
                "call repository unavailable for get operation"
            ) from error

        if row is None:
            raise RecordNotFoundError("call record not found")
        return _record_from_row(row)

    def find(self, call_id: str) -> VersionedCallRecord | None:
        safe_id = _ensure_safe_identifier(call_id, "call_id")

        try:
            row = self._find_row(safe_id)
        except SQLAlchemyError as error:
            raise RepositoryUnavailableError(
                "call repository unavailable for find operation"
            ) from error

        if row is None:
            return None
        return _record_from_row(row)

    def exists(self, call_id: str) -> bool:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        statement = select(calls.c.call_id).where(calls.c.call_id == safe_id).limit(1)

        try:
            return self._connection.execute(statement).first() is not None
        except SQLAlchemyError as error:
            raise RepositoryUnavailableError(
                "call repository unavailable for exists operation"
            ) from error

    def update(
        self,
        call: Call,
        *,
        expected_revision: int,
    ) -> VersionedCallRecord:
        safe_call = _ensure_call(call)
        safe_revision = _ensure_expected_revision(expected_revision)

        try:
            existing_row = self._find_row(safe_call.call_id)
            if existing_row is None:
                raise RecordNotFoundError("call record not found")

            existing = _record_from_row(existing_row)
            if existing.revision != safe_revision:
                raise StaleRecordVersionError("call record revision mismatch")
            if existing.value == safe_call:
                return existing

            next_revision = existing.revision + 1
            values = _call_values(safe_call)
            values.pop("call_id")

            statement = (
                update(calls)
                .where(
                    calls.c.call_id == safe_call.call_id,
                    calls.c.revision == safe_revision,
                )
                .values(
                    **values,
                    revision=next_revision,
                )
                .returning(*calls.c)
            )
            updated_row = self._connection.execute(statement).mappings().first()
        except (
            RecordNotFoundError,
            StaleRecordVersionError,
        ):
            raise
        except SQLAlchemyError as error:
            raise RepositoryUnavailableError(
                "call repository unavailable for update operation"
            ) from error

        if updated_row is None:
            raise StaleRecordVersionError("call record revision mismatch")
        return _record_from_row(updated_row)

    def list_calls(self) -> tuple[VersionedCallRecord, ...]:
        statement = select(calls).order_by(calls.c.call_id)

        try:
            rows = self._connection.execute(statement).mappings()
            return tuple(_record_from_row(row) for row in rows)
        except SQLAlchemyError as error:
            raise RepositoryUnavailableError(
                "call repository unavailable for list operation"
            ) from error

    def _find_row(self, call_id: str) -> RowMapping | None:
        statement = select(calls).where(calls.c.call_id == call_id).limit(1)
        return self._connection.execute(statement).mappings().first()
