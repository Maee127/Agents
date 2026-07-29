"""Call create and read routes."""

from __future__ import annotations

from fastapi import APIRouter, Response

from sales_call_agent.api.dependencies import ApiDependencies
from sales_call_agent.api.mappers import call_create_request_to_domain, versioned_call_to_response
from sales_call_agent.api.schemas.calls import CallCreateRequest, CallResponse
from sales_call_agent.domain.models import Call
from sales_call_agent.persistence.exceptions import RecordAlreadyExistsError
from sales_call_agent.persistence.records import VersionedCallRecord
from sales_call_agent.persistence.unit_of_work import UnitOfWork


def create_calls_router(deps: ApiDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

    @router.post("", status_code=201, response_model=CallResponse)
    def create_call(req: CallCreateRequest, response: Response) -> CallResponse:
        call = call_create_request_to_domain(req)
        uow: UnitOfWork = deps.unit_of_work_factory()
        existing = uow.calls.find(req.call_id)
        if existing is not None:
            if _calls_match(existing.value, call):
                response.status_code = 200
                return _call_response_with_artifacts(uow, existing)
            raise RecordAlreadyExistsError(f"call_id {req.call_id!r} already exists")
        record = uow.calls.add(call)
        uow.commit()
        return versioned_call_to_response(record)

    @router.get("/{call_id}", response_model=CallResponse)
    def get_call(call_id: str) -> CallResponse:
        uow: UnitOfWork = deps.unit_of_work_factory()
        record = uow.calls.get(call_id)
        return _call_response_with_artifacts(uow, record)

    return router


def _calls_match(existing: Call, incoming: Call) -> bool:
    """Return True if metadata/audio match exactly (idempotent duplicate)."""
    a = existing.metadata
    b = incoming.metadata
    return (
        a.call_id == b.call_id
        and a.source_type == b.source_type
        and a.audio_channels == b.audio_channels
        and a.duration_seconds == b.duration_seconds
        and a.original_filename == b.original_filename
        and existing.audio.content_hash == incoming.audio.content_hash
    )


def _call_response_with_artifacts(uow: UnitOfWork, record: VersionedCallRecord) -> CallResponse:
    call_id = record.value.call_id
    pr = uow.processing_results
    return versioned_call_to_response(
        record,
        has_transcription=pr.find_transcription(call_id) is not None,
        has_diarization=pr.find_diarization(call_id) is not None,
        has_alignment=pr.find_alignment(call_id) is not None,
        has_role_assignment=pr.find_role_assignment(call_id) is not None,
    )
