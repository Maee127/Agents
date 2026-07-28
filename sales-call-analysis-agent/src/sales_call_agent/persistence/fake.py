"""Deterministic in-memory persistence repositories and unit of work."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeVar

from sales_call_agent.aggregation.models import CallScoreResult
from sales_call_agent.alignment.models import AlignmentResult
from sales_call_agent.diarization.models import DiarizationResult
from sales_call_agent.domain.models import Call
from sales_call_agent.evaluation.models import CallEvaluationResult
from sales_call_agent.knowledge.models import (
    KnowledgeSection,
    KnowledgeSource,
    RubricStatus,
    SalesRubric,
)
from sales_call_agent.persistence.exceptions import (
    InvalidPersistenceInputError,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleRecordVersionError,
)
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
from sales_call_agent.persistence.repositories import (
    CallProcessingResultRepository,
    CallRepository,
    CallScoreRepository,
    EvaluationRepository,
    KnowledgeRepository,
    RubricRepository,
)
from sales_call_agent.speaker_identity.models import RoleAssignmentResult
from sales_call_agent.transcription.models import TranscriptionResult

_StageResultT = TypeVar(
    "_StageResultT",
    TranscriptionResult,
    DiarizationResult,
    AlignmentResult,
    RoleAssignmentResult,
)


def _ensure_safe_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidPersistenceInputError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise InvalidPersistenceInputError(f"{field_name} must be non-empty and trimmed")
    if "/" in value or "\\" in value or ":" in value:
        raise InvalidPersistenceInputError(f"{field_name} must not contain path-like characters")
    return value


def _ensure_immutable_match(*, existing: object, incoming: object, entity_name: str) -> None:
    if existing != incoming:
        raise RecordAlreadyExistsError(f"{entity_name} already exists with different value")


class FakeFailureOperation(StrEnum):
    """Closed operation identifiers for fake failure injection."""

    CALLS_ADD = "calls_add"
    CALLS_UPDATE = "calls_update"
    PROCESSING_ADD_TRANSCRIPTION = "processing_add_transcription"
    KNOWLEDGE_ADD_SECTIONS = "knowledge_add_sections"
    RUBRICS_UPDATE_STATUS = "rubrics_update_status"
    EVALUATIONS_ADD = "evaluations_add"
    SCORES_ADD = "scores_add"
    UOW_COMMIT = "uow_commit"


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeFailureConfig:
    """Immutable failure configuration for in-memory fake repositories."""

    fail_operations: tuple[FakeFailureOperation, ...] = ()

    def __post_init__(self) -> None:
        seen: set[FakeFailureOperation] = set()
        for operation in self.fail_operations:
            if not isinstance(operation, FakeFailureOperation):
                raise InvalidPersistenceInputError(
                    "fail_operations must contain FakeFailureOperation values"
                )
            if operation in seen:
                raise InvalidPersistenceInputError("fail_operations values must be unique")
            seen.add(operation)

    def should_fail(self, operation: FakeFailureOperation) -> bool:
        return operation in self.fail_operations


@dataclass(slots=True)
class _CommittedState:
    calls: dict[str, VersionedCallRecord]
    transcriptions: dict[str, TranscriptionResult]
    diarizations: dict[str, DiarizationResult]
    alignments: dict[str, AlignmentResult]
    role_assignments: dict[str, RoleAssignmentResult]
    sources: dict[str, VersionedKnowledgeSourceRecord]
    sections_by_id: dict[str, KnowledgeSection]
    sections_by_source: dict[str, tuple[str, ...]]
    rubrics: dict[tuple[str, str], VersionedRubricRecord]
    evaluations: dict[EvaluationKey, CallEvaluationResult]
    scores: dict[CallScoreKey, CallScoreResult]

    def snapshot(self) -> _CommittedState:
        return _CommittedState(
            calls=dict(self.calls),
            transcriptions=dict(self.transcriptions),
            diarizations=dict(self.diarizations),
            alignments=dict(self.alignments),
            role_assignments=dict(self.role_assignments),
            sources=dict(self.sources),
            sections_by_id=dict(self.sections_by_id),
            sections_by_source={
                key: tuple(value) for key, value in self.sections_by_source.items()
            },
            rubrics=dict(self.rubrics),
            evaluations=dict(self.evaluations),
            scores=dict(self.scores),
        )


class InMemoryPersistenceStore:
    """Shared committed-state owner for deterministic in-memory UoW instances."""

    __slots__ = ("_committed", "_revision")

    def __init__(self) -> None:
        self._committed = _CommittedState(
            calls={},
            transcriptions={},
            diarizations={},
            alignments={},
            role_assignments={},
            sources={},
            sections_by_id={},
            sections_by_source={},
            rubrics={},
            evaluations={},
            scores={},
        )
        self._revision = 0

    def checkout(self) -> tuple[int, _CommittedState]:
        return (self._revision, self._committed.snapshot())

    def commit_from(
        self,
        *,
        baseline_revision: int,
        new_state: _CommittedState,
    ) -> int:
        if baseline_revision != self._revision:
            raise StaleRecordVersionError("committed store revision changed")
        self._committed = new_state.snapshot()
        self._revision += 1
        return self._revision

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(revision={self._revision})"


class _InMemoryCallRepository(CallRepository):
    def __init__(self, state: _CommittedState, failure_config: FakeFailureConfig) -> None:
        self._state = state
        self._failure_config = failure_config

    def add(self, call: Call) -> VersionedCallRecord:
        if self._failure_config.should_fail(FakeFailureOperation.CALLS_ADD):
            raise RepositoryUnavailableError("repository unavailable for operation")
        if not isinstance(call, Call):
            raise InvalidPersistenceInputError("call must be a Call")
        call_id = _ensure_safe_identifier(call.call_id, "call_id")
        existing = self._state.calls.get(call_id)
        if existing is None:
            record = VersionedCallRecord(value=call, revision=1)
            self._state.calls[call_id] = record
            return record
        _ensure_immutable_match(existing=existing.value, incoming=call, entity_name="call")
        return existing

    def get(self, call_id: str) -> VersionedCallRecord:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        record = self._state.calls.get(safe_id)
        if record is None:
            raise RecordNotFoundError("call record not found")
        return record

    def find(self, call_id: str) -> VersionedCallRecord | None:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        return self._state.calls.get(safe_id)

    def exists(self, call_id: str) -> bool:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        return safe_id in self._state.calls

    def update(self, call: Call, *, expected_revision: int) -> VersionedCallRecord:
        if self._failure_config.should_fail(FakeFailureOperation.CALLS_UPDATE):
            raise RepositoryUnavailableError("repository unavailable for operation")
        if not isinstance(call, Call):
            raise InvalidPersistenceInputError("call must be a Call")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise InvalidPersistenceInputError("expected_revision must be an integer")
        call_id = _ensure_safe_identifier(call.call_id, "call_id")
        existing = self._state.calls.get(call_id)
        if existing is None:
            raise RecordNotFoundError("call record not found")
        if expected_revision != existing.revision:
            raise StaleRecordVersionError("call record revision mismatch")
        if existing.value == call:
            return existing
        updated = VersionedCallRecord(value=call, revision=existing.revision + 1)
        self._state.calls[call_id] = updated
        return updated

    def list_calls(self) -> tuple[VersionedCallRecord, ...]:
        return tuple(self._state.calls[key] for key in sorted(self._state.calls))


class _InMemoryProcessingResultRepository(CallProcessingResultRepository):
    def __init__(self, state: _CommittedState, failure_config: FakeFailureConfig) -> None:
        self._state = state
        self._failure_config = failure_config

    def add_transcription(self, result: TranscriptionResult) -> None:
        if self._failure_config.should_fail(FakeFailureOperation.PROCESSING_ADD_TRANSCRIPTION):
            raise RepositoryUnavailableError("repository unavailable for operation")
        self._add_stage_result(
            result=result,
            by_call=self._state.transcriptions,
            entity_name="transcription result",
        )

    def get_transcription(self, call_id: str) -> TranscriptionResult:
        return self._get_stage_result(
            call_id=call_id,
            by_call=self._state.transcriptions,
            entity_name="transcription result",
        )

    def find_transcription(self, call_id: str) -> TranscriptionResult | None:
        return self._find_stage_result(call_id=call_id, by_call=self._state.transcriptions)

    def add_diarization(self, result: DiarizationResult) -> None:
        self._add_stage_result(
            result=result,
            by_call=self._state.diarizations,
            entity_name="diarization result",
        )

    def get_diarization(self, call_id: str) -> DiarizationResult:
        return self._get_stage_result(
            call_id=call_id,
            by_call=self._state.diarizations,
            entity_name="diarization result",
        )

    def find_diarization(self, call_id: str) -> DiarizationResult | None:
        return self._find_stage_result(call_id=call_id, by_call=self._state.diarizations)

    def add_alignment(self, result: AlignmentResult) -> None:
        self._add_stage_result(
            result=result,
            by_call=self._state.alignments,
            entity_name="alignment result",
        )

    def get_alignment(self, call_id: str) -> AlignmentResult:
        return self._get_stage_result(
            call_id=call_id,
            by_call=self._state.alignments,
            entity_name="alignment result",
        )

    def find_alignment(self, call_id: str) -> AlignmentResult | None:
        return self._find_stage_result(call_id=call_id, by_call=self._state.alignments)

    def add_role_assignment(self, result: RoleAssignmentResult) -> None:
        self._add_stage_result(
            result=result,
            by_call=self._state.role_assignments,
            entity_name="role-assignment result",
        )

    def get_role_assignment(self, call_id: str) -> RoleAssignmentResult:
        return self._get_stage_result(
            call_id=call_id,
            by_call=self._state.role_assignments,
            entity_name="role-assignment result",
        )

    def find_role_assignment(self, call_id: str) -> RoleAssignmentResult | None:
        return self._find_stage_result(call_id=call_id, by_call=self._state.role_assignments)

    def _add_stage_result(
        self,
        *,
        result: _StageResultT,
        by_call: dict[str, _StageResultT],
        entity_name: str,
    ) -> None:
        call_id = _ensure_safe_identifier(getattr(result, "call_id", None), "call_id")
        existing = by_call.get(call_id)
        if existing is None:
            by_call[call_id] = result
            return
        _ensure_immutable_match(existing=existing, incoming=result, entity_name=entity_name)

    def _get_stage_result(
        self,
        *,
        call_id: str,
        by_call: dict[str, _StageResultT],
        entity_name: str,
    ) -> _StageResultT:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        result = by_call.get(safe_id)
        if result is None:
            raise RecordNotFoundError(f"{entity_name} not found")
        return result

    def _find_stage_result(
        self,
        *,
        call_id: str,
        by_call: dict[str, _StageResultT],
    ) -> _StageResultT | None:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        return by_call.get(safe_id)


class _InMemoryKnowledgeRepository(KnowledgeRepository):
    def __init__(self, state: _CommittedState, failure_config: FakeFailureConfig) -> None:
        self._state = state
        self._failure_config = failure_config

    def add_source(self, source: KnowledgeSource) -> VersionedKnowledgeSourceRecord:
        if not isinstance(source, KnowledgeSource):
            raise InvalidPersistenceInputError("source must be a KnowledgeSource")
        source_id = _ensure_safe_identifier(source.source_id, "source_id")
        existing = self._state.sources.get(source_id)
        if existing is None:
            record = VersionedKnowledgeSourceRecord(value=source, revision=1)
            self._state.sources[source_id] = record
            return record
        _ensure_immutable_match(
            existing=existing.value,
            incoming=source,
            entity_name="knowledge source",
        )
        return existing

    def get_source(self, source_id: str) -> VersionedKnowledgeSourceRecord:
        safe_id = _ensure_safe_identifier(source_id, "source_id")
        record = self._state.sources.get(safe_id)
        if record is None:
            raise RecordNotFoundError("knowledge source not found")
        return record

    def find_source(self, source_id: str) -> VersionedKnowledgeSourceRecord | None:
        safe_id = _ensure_safe_identifier(source_id, "source_id")
        return self._state.sources.get(safe_id)

    def update_source(
        self,
        source: KnowledgeSource,
        *,
        expected_revision: int,
    ) -> VersionedKnowledgeSourceRecord:
        if not isinstance(source, KnowledgeSource):
            raise InvalidPersistenceInputError("source must be a KnowledgeSource")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise InvalidPersistenceInputError("expected_revision must be an integer")
        source_id = _ensure_safe_identifier(source.source_id, "source_id")
        existing = self._state.sources.get(source_id)
        if existing is None:
            raise RecordNotFoundError("knowledge source not found")
        if existing.revision != expected_revision:
            raise StaleRecordVersionError("knowledge source revision mismatch")
        if existing.value == source:
            return existing
        updated = VersionedKnowledgeSourceRecord(value=source, revision=existing.revision + 1)
        self._state.sources[source_id] = updated
        return updated

    def list_sources(self) -> tuple[VersionedKnowledgeSourceRecord, ...]:
        return tuple(self._state.sources[key] for key in sorted(self._state.sources))

    def add_sections(self, source_id: str, sections: tuple[KnowledgeSection, ...]) -> None:
        if self._failure_config.should_fail(FakeFailureOperation.KNOWLEDGE_ADD_SECTIONS):
            raise RepositoryUnavailableError("repository unavailable for operation")
        safe_source_id = _ensure_safe_identifier(source_id, "source_id")
        if safe_source_id not in self._state.sources:
            raise RecordNotFoundError("knowledge source not found")
        if not isinstance(sections, tuple):
            raise InvalidPersistenceInputError("sections must be a tuple")
        if not sections:
            return

        seen_ids: set[str] = set()
        pending_adds: dict[str, KnowledgeSection] = {}
        for section in sections:
            if not isinstance(section, KnowledgeSection):
                raise InvalidPersistenceInputError("sections must contain KnowledgeSection values")
            if section.source_id != safe_source_id:
                raise InvalidPersistenceInputError(
                    "section source_id must match supplied source_id"
                )
            if section.section_id in seen_ids:
                raise InvalidPersistenceInputError("sections must contain unique section IDs")
            seen_ids.add(section.section_id)

            existing = self._state.sections_by_id.get(section.section_id)
            if existing is not None and existing != section:
                raise RecordAlreadyExistsError(
                    "knowledge section already exists with different value"
                )
            if existing is None:
                pending_adds[section.section_id] = section

        for section_id, section in pending_adds.items():
            self._state.sections_by_id[section_id] = section

        current_ids = list(self._state.sections_by_source.get(safe_source_id, ()))
        for section in pending_adds.values():
            current_ids.append(section.section_id)
        ordered_ids = tuple(
            sorted(
                current_ids,
                key=lambda key: (
                    self._state.sections_by_id[key].source_id,
                    self._state.sections_by_id[key].ordinal,
                    key,
                ),
            )
        )
        self._state.sections_by_source[safe_source_id] = ordered_ids

    def get_sections(self, source_id: str) -> tuple[KnowledgeSection, ...]:
        safe_id = _ensure_safe_identifier(source_id, "source_id")
        ids = self._state.sections_by_source.get(safe_id, ())
        return tuple(self._state.sections_by_id[section_id] for section_id in ids)

    def find_section(self, section_id: str) -> KnowledgeSection | None:
        safe_id = _ensure_safe_identifier(section_id, "section_id")
        return self._state.sections_by_id.get(safe_id)


class _InMemoryRubricRepository(RubricRepository):
    def __init__(self, state: _CommittedState, failure_config: FakeFailureConfig) -> None:
        self._state = state
        self._failure_config = failure_config

    def add(self, rubric: SalesRubric) -> VersionedRubricRecord:
        if not isinstance(rubric, SalesRubric):
            raise InvalidPersistenceInputError("rubric must be a SalesRubric")
        key = (
            _ensure_safe_identifier(rubric.rubric_id, "rubric_id"),
            rubric.version,
        )
        existing = self._state.rubrics.get(key)
        if existing is None:
            record = VersionedRubricRecord(value=rubric, revision=1)
            self._state.rubrics[key] = record
            return record
        _ensure_immutable_match(
            existing=existing.value,
            incoming=rubric,
            entity_name="rubric revision",
        )
        return existing

    def get(self, rubric_id: str, version: str) -> VersionedRubricRecord:
        record = self.find(rubric_id, version)
        if record is None:
            raise RecordNotFoundError("rubric revision not found")
        return record

    def find(self, rubric_id: str, version: str) -> VersionedRubricRecord | None:
        safe_id = _ensure_safe_identifier(rubric_id, "rubric_id")
        return self._state.rubrics.get((safe_id, version))

    def update_status(
        self,
        rubric_id: str,
        version: str,
        *,
        status: RubricStatus,
        expected_revision: int,
    ) -> VersionedRubricRecord:
        if self._failure_config.should_fail(FakeFailureOperation.RUBRICS_UPDATE_STATUS):
            raise RepositoryUnavailableError("repository unavailable for operation")
        safe_id = _ensure_safe_identifier(rubric_id, "rubric_id")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise InvalidPersistenceInputError("expected_revision must be an integer")
        key = (safe_id, version)
        existing = self._state.rubrics.get(key)
        if existing is None:
            raise RecordNotFoundError("rubric revision not found")
        if existing.revision != expected_revision:
            raise StaleRecordVersionError("rubric revision mismatch")
        if not isinstance(status, RubricStatus):
            raise InvalidPersistenceInputError("status must be a RubricStatus")
        if status is existing.value.status:
            return existing
        if not _is_allowed_rubric_status_transition(existing.value.status, status):
            raise RecordAlreadyExistsError("rubric status transition is not allowed")
        updated_rubric = replace(existing.value, status=status)
        updated = VersionedRubricRecord(value=updated_rubric, revision=existing.revision + 1)
        self._state.rubrics[key] = updated
        return updated

    def list_versions(self, rubric_id: str) -> tuple[VersionedRubricRecord, ...]:
        safe_id = _ensure_safe_identifier(rubric_id, "rubric_id")
        filtered = [
            record
            for (candidate_id, _version), record in self._state.rubrics.items()
            if candidate_id == safe_id
        ]
        return tuple(sorted(filtered, key=lambda record: parse_semver_core(record.value.version)))

    def get_latest_approved(self, rubric_id: str) -> VersionedRubricRecord:
        record = self.find_latest_approved(rubric_id)
        if record is None:
            raise RecordNotFoundError("approved rubric revision not found")
        return record

    def find_latest_approved(self, rubric_id: str) -> VersionedRubricRecord | None:
        versions = self.list_versions(rubric_id)
        approved = [record for record in versions if record.value.status is RubricStatus.APPROVED]
        if not approved:
            return None
        return approved[-1]


def _is_allowed_rubric_status_transition(current: RubricStatus, new: RubricStatus) -> bool:
    allowed: dict[RubricStatus, tuple[RubricStatus, ...]] = {
        RubricStatus.DRAFT: (RubricStatus.APPROVED, RubricStatus.RETIRED),
        RubricStatus.APPROVED: (RubricStatus.RETIRED,),
        RubricStatus.RETIRED: (),
    }
    return new in allowed[current]


class _InMemoryEvaluationRepository(EvaluationRepository):
    def __init__(self, state: _CommittedState, failure_config: FakeFailureConfig) -> None:
        self._state = state
        self._failure_config = failure_config

    def add(self, result: CallEvaluationResult) -> EvaluationKey:
        if self._failure_config.should_fail(FakeFailureOperation.EVALUATIONS_ADD):
            raise RepositoryUnavailableError("repository unavailable for operation")
        if not isinstance(result, CallEvaluationResult):
            raise InvalidPersistenceInputError("result must be a CallEvaluationResult")
        key = EvaluationKey(
            call_id=result.call_id,
            rubric_id=result.rubric_id,
            rubric_version=result.rubric_version,
            provider_name=result.provider_name,
            model_name=result.model_name,
        )
        existing = self._state.evaluations.get(key)
        if existing is None:
            self._state.evaluations[key] = result
            return key
        _ensure_immutable_match(existing=existing, incoming=result, entity_name="evaluation result")
        return key

    def get(self, key: EvaluationKey) -> CallEvaluationResult:
        if not isinstance(key, EvaluationKey):
            raise InvalidPersistenceInputError("key must be an EvaluationKey")
        result = self._state.evaluations.get(key)
        if result is None:
            raise RecordNotFoundError("evaluation result not found")
        return result

    def find(self, key: EvaluationKey) -> CallEvaluationResult | None:
        if not isinstance(key, EvaluationKey):
            raise InvalidPersistenceInputError("key must be an EvaluationKey")
        return self._state.evaluations.get(key)

    def list_for_call(self, call_id: str) -> tuple[CallEvaluationResult, ...]:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        pairs = [
            (key, value) for key, value in self._state.evaluations.items() if key.call_id == safe_id
        ]
        pairs.sort(key=lambda pair: pair[0].sort_key)
        return tuple(value for _key, value in pairs)

    def list_for_call_rubric(
        self,
        call_id: str,
        rubric_id: str,
        rubric_version: str,
    ) -> tuple[CallEvaluationResult, ...]:
        safe_call = _ensure_safe_identifier(call_id, "call_id")
        safe_rubric = _ensure_safe_identifier(rubric_id, "rubric_id")
        pairs = [
            (key, value)
            for key, value in self._state.evaluations.items()
            if key.call_id == safe_call
            and key.rubric_id == safe_rubric
            and key.rubric_version == rubric_version
        ]
        pairs.sort(key=lambda pair: pair[0].sort_key)
        return tuple(value for _key, value in pairs)


class _InMemoryCallScoreRepository(CallScoreRepository):
    def __init__(self, state: _CommittedState, failure_config: FakeFailureConfig) -> None:
        self._state = state
        self._failure_config = failure_config

    def add(self, result: CallScoreResult, *, evaluation_key: EvaluationKey) -> CallScoreKey:
        if self._failure_config.should_fail(FakeFailureOperation.SCORES_ADD):
            raise RepositoryUnavailableError("repository unavailable for operation")
        if not isinstance(result, CallScoreResult):
            raise InvalidPersistenceInputError("result must be a CallScoreResult")
        if not isinstance(evaluation_key, EvaluationKey):
            raise InvalidPersistenceInputError("evaluation_key must be an EvaluationKey")
        if result.call_id != evaluation_key.call_id:
            raise InvalidPersistenceInputError("call-score and evaluation key call_id must match")
        if result.rubric_id != evaluation_key.rubric_id:
            raise InvalidPersistenceInputError("call-score and evaluation key rubric_id must match")
        if result.rubric_version != evaluation_key.rubric_version:
            raise InvalidPersistenceInputError(
                "call-score and evaluation key rubric_version must match"
            )
        key = CallScoreKey(
            evaluation_key=evaluation_key,
            aggregation_policy_fingerprint=aggregation_policy_fingerprint(result.config),
        )
        existing = self._state.scores.get(key)
        if existing is None:
            self._state.scores[key] = result
            return key
        _ensure_immutable_match(existing=existing, incoming=result, entity_name="call-score result")
        return key

    def get(self, key: CallScoreKey) -> CallScoreResult:
        if not isinstance(key, CallScoreKey):
            raise InvalidPersistenceInputError("key must be a CallScoreKey")
        result = self._state.scores.get(key)
        if result is None:
            raise RecordNotFoundError("call-score result not found")
        return result

    def find(self, key: CallScoreKey) -> CallScoreResult | None:
        if not isinstance(key, CallScoreKey):
            raise InvalidPersistenceInputError("key must be a CallScoreKey")
        return self._state.scores.get(key)

    def list_for_evaluation(self, key: EvaluationKey) -> tuple[CallScoreResult, ...]:
        if not isinstance(key, EvaluationKey):
            raise InvalidPersistenceInputError("key must be an EvaluationKey")
        pairs = [
            (score_key, value)
            for score_key, value in self._state.scores.items()
            if score_key.evaluation_key == key
        ]
        pairs.sort(key=lambda pair: pair[0].sort_key)
        return tuple(value for _key, value in pairs)

    def list_for_call(self, call_id: str) -> tuple[CallScoreResult, ...]:
        safe_id = _ensure_safe_identifier(call_id, "call_id")
        pairs = [
            (key, value)
            for key, value in self._state.scores.items()
            if key.evaluation_key.call_id == safe_id
        ]
        pairs.sort(key=lambda pair: pair[0].sort_key)
        return tuple(value for _key, value in pairs)


class InMemoryUnitOfWork:
    """Optimistic shared-store in-memory unit-of-work implementation."""

    __slots__ = (
        "_baseline_revision",
        "_failure_config",
        "_store",
        "_working_state",
        "call_scores",
        "calls",
        "evaluations",
        "knowledge",
        "processing_results",
        "rubrics",
    )

    def __init__(
        self,
        *,
        store: InMemoryPersistenceStore,
        failure_config: FakeFailureConfig | None = None,
    ) -> None:
        if not isinstance(store, InMemoryPersistenceStore):
            raise InvalidPersistenceInputError("store must be an InMemoryPersistenceStore")
        self._store = store
        self._failure_config = failure_config or FakeFailureConfig()
        self._baseline_revision, self._working_state = store.checkout()
        self.calls = _InMemoryCallRepository(self._working_state, self._failure_config)
        self.processing_results = _InMemoryProcessingResultRepository(
            self._working_state, self._failure_config
        )
        self.knowledge = _InMemoryKnowledgeRepository(self._working_state, self._failure_config)
        self.rubrics = _InMemoryRubricRepository(self._working_state, self._failure_config)
        self.evaluations = _InMemoryEvaluationRepository(self._working_state, self._failure_config)
        self.call_scores = _InMemoryCallScoreRepository(self._working_state, self._failure_config)

    def commit(self) -> None:
        if self._failure_config.should_fail(FakeFailureOperation.UOW_COMMIT):
            raise RepositoryUnavailableError("repository unavailable for operation")
        new_revision = self._store.commit_from(
            baseline_revision=self._baseline_revision,
            new_state=self._working_state,
        )
        self._baseline_revision = new_revision
        self._working_state = self._working_state.snapshot()
        self._rebind_repositories()

    def rollback(self) -> None:
        self._baseline_revision, self._working_state = self._store.checkout()
        self._rebind_repositories()

    def _rebind_repositories(self) -> None:
        self.calls = _InMemoryCallRepository(self._working_state, self._failure_config)
        self.processing_results = _InMemoryProcessingResultRepository(
            self._working_state, self._failure_config
        )
        self.knowledge = _InMemoryKnowledgeRepository(self._working_state, self._failure_config)
        self.rubrics = _InMemoryRubricRepository(self._working_state, self._failure_config)
        self.evaluations = _InMemoryEvaluationRepository(self._working_state, self._failure_config)
        self.call_scores = _InMemoryCallScoreRepository(self._working_state, self._failure_config)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(baseline_revision={self._baseline_revision})"
