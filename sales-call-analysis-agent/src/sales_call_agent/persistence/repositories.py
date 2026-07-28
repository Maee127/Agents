"""Provider-independent repository protocols for persistence operations."""

from __future__ import annotations

from typing import Protocol

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
from sales_call_agent.persistence.keys import CallScoreKey, EvaluationKey
from sales_call_agent.persistence.records import (
    VersionedCallRecord,
    VersionedKnowledgeSourceRecord,
    VersionedRubricRecord,
)
from sales_call_agent.speaker_identity.models import RoleAssignmentResult
from sales_call_agent.transcription.models import TranscriptionResult


class CallRepository(Protocol):
    """Persistence contract for the mutable call aggregate."""

    def add(self, call: Call) -> VersionedCallRecord: ...

    def get(self, call_id: str) -> VersionedCallRecord: ...

    def find(self, call_id: str) -> VersionedCallRecord | None: ...

    def exists(self, call_id: str) -> bool: ...

    def update(self, call: Call, *, expected_revision: int) -> VersionedCallRecord: ...

    def list_calls(self) -> tuple[VersionedCallRecord, ...]: ...


class CallProcessingResultRepository(Protocol):
    """Persistence contract for canonical stage results per call."""

    def add_transcription(self, result: TranscriptionResult) -> None: ...

    def get_transcription(self, call_id: str) -> TranscriptionResult: ...

    def find_transcription(self, call_id: str) -> TranscriptionResult | None: ...

    def add_diarization(self, result: DiarizationResult) -> None: ...

    def get_diarization(self, call_id: str) -> DiarizationResult: ...

    def find_diarization(self, call_id: str) -> DiarizationResult | None: ...

    def add_alignment(self, result: AlignmentResult) -> None: ...

    def get_alignment(self, call_id: str) -> AlignmentResult: ...

    def find_alignment(self, call_id: str) -> AlignmentResult | None: ...

    def add_role_assignment(self, result: RoleAssignmentResult) -> None: ...

    def get_role_assignment(self, call_id: str) -> RoleAssignmentResult: ...

    def find_role_assignment(self, call_id: str) -> RoleAssignmentResult | None: ...


class KnowledgeRepository(Protocol):
    """Persistence contract for knowledge-source aggregate and immutable sections."""

    def add_source(self, source: KnowledgeSource) -> VersionedKnowledgeSourceRecord: ...

    def get_source(self, source_id: str) -> VersionedKnowledgeSourceRecord: ...

    def find_source(self, source_id: str) -> VersionedKnowledgeSourceRecord | None: ...

    def update_source(
        self,
        source: KnowledgeSource,
        *,
        expected_revision: int,
    ) -> VersionedKnowledgeSourceRecord: ...

    def list_sources(self) -> tuple[VersionedKnowledgeSourceRecord, ...]: ...

    def add_sections(self, source_id: str, sections: tuple[KnowledgeSection, ...]) -> None: ...

    def get_sections(self, source_id: str) -> tuple[KnowledgeSection, ...]: ...

    def find_section(self, section_id: str) -> KnowledgeSection | None: ...


class RubricRepository(Protocol):
    """Persistence contract for rubric revisions and status transitions."""

    def add(self, rubric: SalesRubric) -> VersionedRubricRecord: ...

    def get(self, rubric_id: str, version: str) -> VersionedRubricRecord: ...

    def find(self, rubric_id: str, version: str) -> VersionedRubricRecord | None: ...

    def update_status(
        self,
        rubric_id: str,
        version: str,
        *,
        status: RubricStatus,
        expected_revision: int,
    ) -> VersionedRubricRecord: ...

    def list_versions(self, rubric_id: str) -> tuple[VersionedRubricRecord, ...]: ...

    def get_latest_approved(self, rubric_id: str) -> VersionedRubricRecord: ...

    def find_latest_approved(self, rubric_id: str) -> VersionedRubricRecord | None: ...


class EvaluationRepository(Protocol):
    """Persistence contract for immutable call evaluation records."""

    def add(self, result: CallEvaluationResult) -> EvaluationKey: ...

    def get(self, key: EvaluationKey) -> CallEvaluationResult: ...

    def find(self, key: EvaluationKey) -> CallEvaluationResult | None: ...

    def list_for_call(self, call_id: str) -> tuple[CallEvaluationResult, ...]: ...

    def list_for_call_rubric(
        self,
        call_id: str,
        rubric_id: str,
        rubric_version: str,
    ) -> tuple[CallEvaluationResult, ...]: ...


class CallScoreRepository(Protocol):
    """Persistence contract for immutable call-score records."""

    def add(self, result: CallScoreResult, *, evaluation_key: EvaluationKey) -> CallScoreKey: ...

    def get(self, key: CallScoreKey) -> CallScoreResult: ...

    def find(self, key: CallScoreKey) -> CallScoreResult | None: ...

    def list_for_evaluation(self, key: EvaluationKey) -> tuple[CallScoreResult, ...]: ...

    def list_for_call(self, call_id: str) -> tuple[CallScoreResult, ...]: ...
