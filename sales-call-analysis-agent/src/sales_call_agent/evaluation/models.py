"""Provider-independent models for criterion-level call evaluation."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sales_call_agent.alignment.models import AlignmentResult
from sales_call_agent.evaluation.exceptions import (
    InvalidEvaluationInputError,
    InvalidEvaluationResponseError,
)
from sales_call_agent.knowledge.models import RubricStatus, SalesRubric
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentResult,
    SpeakerRole,
)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_WARNING_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SPEAKER_LABEL_RE = re.compile(r"^SPEAKER_[0-9]{2,}$")


class CriterionEvaluationStatus(StrEnum):
    """Primary criterion-level evaluation status."""

    SCORED = "scored"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CriterionEvaluationReason(StrEnum):
    """Primary criterion-level evaluation reason code."""

    SUPPORTED_BY_TRANSCRIPT_EVIDENCE = "supported_by_transcript_evidence"
    SUPPORTED_BY_ABSENCE_EVIDENCE = "supported_by_absence_evidence"
    REQUIRED_ROLE_NOT_PRESENT = "required_role_not_present"
    CALL_CONTEXT_NOT_APPLICABLE = "call_context_not_applicable"
    NO_VALID_EVIDENCE = "no_valid_evidence"
    INSUFFICIENT_EVIDENCE_SPANS = "insufficient_evidence_spans"
    SELLER_ROLE_UNRESOLVED = "seller_role_unresolved"
    CUSTOMER_CONTEXT_MISSING = "customer_context_missing"
    TIMESTAMP_EVIDENCE_MISSING = "timestamp_evidence_missing"


class HumanReviewReason(StrEnum):
    """Reason why a criterion result requires human review."""

    RUBRIC_REQUIRES_HUMAN_REVIEW = "rubric_requires_human_review"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    AMBIGUOUS_SPEAKER_ROLE = "ambiguous_speaker_role"
    PROVIDER_UNCERTAINTY = "provider_uncertainty"


class AbsenceEvidenceReason(StrEnum):
    """Reason category for structured absence evidence."""

    EXPECTED_BEHAVIOR_NOT_OBSERVED = "expected_behavior_not_observed"
    PROHIBITED_BEHAVIOR_NOT_PRESENT = "prohibited_behavior_not_present"


class EvaluationQualityFlag(StrEnum):
    """Quality conditions for one call-level evaluation result."""

    INSUFFICIENT_EVIDENCE_PRESENT = "insufficient_evidence_present"
    NOT_APPLICABLE_CRITERIA_PRESENT = "not_applicable_criteria_present"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    UNKNOWN_SPEAKER_ROLES_PRESENT = "unknown_speaker_roles_present"
    ABSENCE_EVIDENCE_USED = "absence_evidence_used"
    PARTIAL_EVALUATION = "partial_evaluation"
    ALL_CRITERIA_SCORED = "all_criteria_scored"
    PROVIDER_WARNING = "provider_warning"


def _ensure_required_string(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise error(f"{field_name} must be non-empty and trimmed")


def _ensure_safe_identifier(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe identifier")
    if "/" in value or "\\" in value or ":" in value:
        raise error(f"{field_name} must not contain path-like characters")


def _ensure_safe_warning_code(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SAFE_WARNING_CODE_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe warning code")


def _ensure_enum_member(
    value: object, enum_type: type[Enum], field_name: str, error: type[Exception]
) -> None:
    if not isinstance(value, enum_type):
        raise error(f"{field_name} must be a {enum_type.__name__} member")


def _ensure_non_negative_integer(value: object, field_name: str, error: type[Exception]) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error(f"{field_name} must be an integer")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _ensure_finite_non_negative_number(
    value: object, field_name: str, error: type[Exception]
) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error(f"{field_name} must be a number")
    if not math.isfinite(value):
        raise error(f"{field_name} must be finite")
    if value < 0:
        raise error(f"{field_name} must not be negative")


def _ensure_speaker_label(value: object, field_name: str, error: type[Exception]) -> None:
    _ensure_required_string(value, field_name, error)
    assert isinstance(value, str)
    if not _SPEAKER_LABEL_RE.fullmatch(value):
        raise error(f"{field_name} must match the canonical speaker label format")


def _is_not_applicable_reason(reason: CriterionEvaluationReason) -> bool:
    return reason in {
        CriterionEvaluationReason.REQUIRED_ROLE_NOT_PRESENT,
        CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
    }


def _is_insufficient_reason(reason: CriterionEvaluationReason) -> bool:
    return reason in {
        CriterionEvaluationReason.NO_VALID_EVIDENCE,
        CriterionEvaluationReason.INSUFFICIENT_EVIDENCE_SPANS,
        CriterionEvaluationReason.SELLER_ROLE_UNRESOLVED,
        CriterionEvaluationReason.CUSTOMER_CONTEXT_MISSING,
        CriterionEvaluationReason.TIMESTAMP_EVIDENCE_MISSING,
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptEvidenceSpan:
    """Stable transcript reference for criterion evidence without text duplication."""

    source_segment_index: int
    source_word_start_index: int | None = None
    source_word_end_index: int | None = None
    speaker_label: str
    speaker_role: SpeakerRole
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_non_negative_integer(
            self.source_segment_index,
            "source_segment_index",
            InvalidEvaluationResponseError,
        )
        if (self.source_word_start_index is None) != (self.source_word_end_index is None):
            raise InvalidEvaluationResponseError(
                "source_word_start_index and source_word_end_index must be provided together"
            )
        if self.source_word_start_index is not None and self.source_word_end_index is not None:
            _ensure_non_negative_integer(
                self.source_word_start_index,
                "source_word_start_index",
                InvalidEvaluationResponseError,
            )
            _ensure_non_negative_integer(
                self.source_word_end_index,
                "source_word_end_index",
                InvalidEvaluationResponseError,
            )
            if self.source_word_end_index < self.source_word_start_index:
                raise InvalidEvaluationResponseError(
                    "source_word_end_index must be >= source_word_start_index"
                )
        _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidEvaluationResponseError)
        _ensure_enum_member(
            self.speaker_role,
            SpeakerRole,
            "speaker_role",
            InvalidEvaluationResponseError,
        )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidEvaluationResponseError)


@dataclass(frozen=True, slots=True, kw_only=True)
class AbsenceEvidence:
    """Structured evidence describing reviewed scope where behavior was absent."""

    scope_start_seconds: float
    scope_end_seconds: float
    speaker_role: SpeakerRole | None
    reason_code: AbsenceEvidenceReason
    reviewed_segment_indexes: tuple[int, ...]
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_finite_non_negative_number(
            self.scope_start_seconds,
            "scope_start_seconds",
            InvalidEvaluationResponseError,
        )
        _ensure_finite_non_negative_number(
            self.scope_end_seconds,
            "scope_end_seconds",
            InvalidEvaluationResponseError,
        )
        if self.scope_end_seconds <= self.scope_start_seconds:
            raise InvalidEvaluationResponseError("scope_end_seconds must be > scope_start_seconds")
        if self.speaker_role is not None:
            _ensure_enum_member(
                self.speaker_role,
                SpeakerRole,
                "speaker_role",
                InvalidEvaluationResponseError,
            )
        _ensure_enum_member(
            self.reason_code,
            AbsenceEvidenceReason,
            "reason_code",
            InvalidEvaluationResponseError,
        )
        if not self.reviewed_segment_indexes:
            raise InvalidEvaluationResponseError(
                "reviewed_segment_indexes must contain at least one segment index"
            )
        previous_index: int | None = None
        seen_indexes: set[int] = set()
        for value in self.reviewed_segment_indexes:
            _ensure_non_negative_integer(
                value,
                "reviewed_segment_indexes",
                InvalidEvaluationResponseError,
            )
            if value in seen_indexes:
                raise InvalidEvaluationResponseError("reviewed_segment_indexes must be unique")
            seen_indexes.add(value)
            if previous_index is not None and value <= previous_index:
                raise InvalidEvaluationResponseError(
                    "reviewed_segment_indexes must be strictly increasing"
                )
            previous_index = value
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidEvaluationResponseError)


@dataclass(frozen=True, slots=True, kw_only=True)
class CriterionEvaluation:
    """Evaluation outcome for one rubric criterion."""

    criterion_id: str
    status: CriterionEvaluationStatus
    reason_code: CriterionEvaluationReason
    score: float | None = None
    score_level_label: str | None = None
    evidence_spans: tuple[TranscriptEvidenceSpan, ...] = ()
    absence_evidence: AbsenceEvidence | None = None
    human_review_required: bool = False
    human_review_reason: HumanReviewReason | None = None
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_safe_identifier(self.criterion_id, "criterion_id", InvalidEvaluationResponseError)
        _ensure_enum_member(
            self.status,
            CriterionEvaluationStatus,
            "status",
            InvalidEvaluationResponseError,
        )
        _ensure_enum_member(
            self.reason_code,
            CriterionEvaluationReason,
            "reason_code",
            InvalidEvaluationResponseError,
        )

        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, int | float):
                raise InvalidEvaluationResponseError("score must be a number")
            if not math.isfinite(float(self.score)):
                raise InvalidEvaluationResponseError("score must be finite")
        if self.score_level_label is not None:
            _ensure_required_string(
                self.score_level_label,
                "score_level_label",
                InvalidEvaluationResponseError,
            )

        _validate_evidence_spans(self.evidence_spans)
        if self.absence_evidence is not None and not isinstance(
            self.absence_evidence,
            AbsenceEvidence,
        ):
            raise InvalidEvaluationResponseError("absence_evidence must be an AbsenceEvidence")

        if not isinstance(self.human_review_required, bool):
            raise InvalidEvaluationResponseError("human_review_required must be a boolean")
        if self.human_review_required:
            if self.human_review_reason is None:
                raise InvalidEvaluationResponseError(
                    "human_review_reason is required when human_review_required is true"
                )
            _ensure_enum_member(
                self.human_review_reason,
                HumanReviewReason,
                "human_review_reason",
                InvalidEvaluationResponseError,
            )
        elif self.human_review_reason is not None:
            raise InvalidEvaluationResponseError(
                "human_review_reason must be absent when human_review_required is false"
            )

        if self.status is CriterionEvaluationStatus.SCORED:
            if self.score is None or self.score_level_label is None:
                raise InvalidEvaluationResponseError(
                    "scored status requires score and score_level_label"
                )
            has_transcript_evidence = bool(self.evidence_spans)
            has_absence_evidence = self.absence_evidence is not None
            if has_transcript_evidence == has_absence_evidence:
                raise InvalidEvaluationResponseError(
                    "scored status requires exactly one evidence form"
                )
            if has_transcript_evidence and (
                self.reason_code is not CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE
            ):
                raise InvalidEvaluationResponseError(
                    "scored transcript evidence requires transcript support reason"
                )
            if has_absence_evidence and (
                self.reason_code is not CriterionEvaluationReason.SUPPORTED_BY_ABSENCE_EVIDENCE
            ):
                raise InvalidEvaluationResponseError(
                    "scored absence evidence requires absence support reason"
                )
        elif self.status is CriterionEvaluationStatus.NOT_APPLICABLE:
            if self.score is not None or self.score_level_label is not None:
                raise InvalidEvaluationResponseError(
                    "not_applicable status requires score fields to be absent"
                )
            if self.evidence_spans or self.absence_evidence is not None:
                raise InvalidEvaluationResponseError(
                    "not_applicable status forbids evidence spans and absence evidence"
                )
            if not _is_not_applicable_reason(self.reason_code):
                raise InvalidEvaluationResponseError(
                    "not_applicable status requires a not-applicable reason"
                )
        elif self.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE:
            if self.score is not None or self.score_level_label is not None:
                raise InvalidEvaluationResponseError(
                    "insufficient_evidence status requires score fields to be absent"
                )
            if self.absence_evidence is not None:
                raise InvalidEvaluationResponseError(
                    "insufficient_evidence status forbids absence evidence"
                )
            if not _is_insufficient_reason(self.reason_code):
                raise InvalidEvaluationResponseError(
                    "insufficient_evidence status requires an insufficient reason"
                )

        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidEvaluationResponseError)


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationRequest:
    """Input contract for evaluating one call against one approved rubric."""

    call_id: str
    alignment: AlignmentResult = field(repr=False)
    role_assignment: RoleAssignmentResult = field(repr=False)
    rubric: SalesRubric = field(repr=False)
    provider_config_id: str | None = None
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidEvaluationInputError)
        if not isinstance(self.alignment, AlignmentResult):
            raise InvalidEvaluationInputError("alignment must be an AlignmentResult")
        if not isinstance(self.role_assignment, RoleAssignmentResult):
            raise InvalidEvaluationInputError("role_assignment must be a RoleAssignmentResult")
        if not isinstance(self.rubric, SalesRubric):
            raise InvalidEvaluationInputError("rubric must be a SalesRubric")
        if self.alignment.call_id != self.call_id:
            raise InvalidEvaluationInputError("alignment call_id does not match request call_id")
        if self.role_assignment.call_id != self.call_id:
            raise InvalidEvaluationInputError(
                "role_assignment call_id does not match request call_id"
            )
        if self.rubric.status is not RubricStatus.APPROVED:
            raise InvalidEvaluationInputError("rubric status must be APPROVED")
        if not self.rubric.criteria:
            raise InvalidEvaluationInputError("approved rubric must contain at least one criterion")
        if self.provider_config_id is not None:
            _ensure_safe_identifier(
                self.provider_config_id,
                "provider_config_id",
                InvalidEvaluationInputError,
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidEvaluationInputError)

        alignment_labels = self.alignment.speaker_labels
        role_labels = tuple(
            assignment.speaker_label for assignment in self.role_assignment.assignments
        )
        if alignment_labels != role_labels:
            raise InvalidEvaluationInputError(
                "role_assignment speaker labels must exactly match alignment speaker labels order"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CallEvaluationResult:
    """Call-level criterion evaluation output."""

    call_id: str
    rubric_id: str
    rubric_version: str
    provider_name: str
    model_name: str
    criterion_evaluations: tuple[CriterionEvaluation, ...]
    quality_flags: tuple[EvaluationQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidEvaluationResponseError)
        _ensure_safe_identifier(self.rubric_id, "rubric_id", InvalidEvaluationResponseError)
        _ensure_required_string(
            self.rubric_version,
            "rubric_version",
            InvalidEvaluationResponseError,
        )
        _ensure_safe_identifier(
            self.provider_name,
            "provider_name",
            InvalidEvaluationResponseError,
        )
        _ensure_safe_identifier(self.model_name, "model_name", InvalidEvaluationResponseError)

        seen_ids: set[str] = set()
        for item in self.criterion_evaluations:
            if not isinstance(item, CriterionEvaluation):
                raise InvalidEvaluationResponseError(
                    "criterion_evaluations must contain CriterionEvaluation values"
                )
            if item.criterion_id in seen_ids:
                raise InvalidEvaluationResponseError("criterion evaluation IDs must be unique")
            seen_ids.add(item.criterion_id)

        for flag in self.quality_flags:
            _ensure_enum_member(
                flag,
                EvaluationQualityFlag,
                "quality_flags",
                InvalidEvaluationResponseError,
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidEvaluationResponseError)

        _validate_quality_flag_consistency(
            self.criterion_evaluations,
            self.quality_flags,
            self.warning_codes,
        )

    @property
    def scored_count(self) -> int:
        return sum(
            1
            for item in self.criterion_evaluations
            if item.status is CriterionEvaluationStatus.SCORED
        )

    @property
    def not_applicable_count(self) -> int:
        return sum(
            1
            for item in self.criterion_evaluations
            if item.status is CriterionEvaluationStatus.NOT_APPLICABLE
        )

    @property
    def insufficient_evidence_count(self) -> int:
        return sum(
            1
            for item in self.criterion_evaluations
            if item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
        )

    @property
    def human_review_count(self) -> int:
        return sum(1 for item in self.criterion_evaluations if item.human_review_required)

    @property
    def criterion_ids(self) -> tuple[str, ...]:
        return tuple(item.criterion_id for item in self.criterion_evaluations)


def _validate_evidence_spans(spans: Sequence[TranscriptEvidenceSpan]) -> None:
    previous_key: tuple[int, int, int, str] | None = None
    seen: set[tuple[int, int, int, str, SpeakerRole]] = set()
    for span in spans:
        if not isinstance(span, TranscriptEvidenceSpan):
            raise InvalidEvaluationResponseError(
                "evidence_spans must contain TranscriptEvidenceSpan values"
            )
        start = span.source_word_start_index if span.source_word_start_index is not None else -1
        end = span.source_word_end_index if span.source_word_end_index is not None else -1
        dedupe_key = (
            span.source_segment_index,
            start,
            end,
            span.speaker_label,
            span.speaker_role,
        )
        if dedupe_key in seen:
            raise InvalidEvaluationResponseError("evidence_spans must be unique")
        seen.add(dedupe_key)
        ordering_key = (span.source_segment_index, start, end, span.speaker_label)
        if previous_key is not None and ordering_key < previous_key:
            raise InvalidEvaluationResponseError("evidence_spans must be deterministically ordered")
        previous_key = ordering_key


def _validate_quality_flag_consistency(
    criterion_evaluations: Sequence[CriterionEvaluation],
    quality_flags: Sequence[EvaluationQualityFlag],
    warning_codes: Sequence[str],
) -> None:
    flag_set = set(quality_flags)
    scored = [
        item for item in criterion_evaluations if item.status is CriterionEvaluationStatus.SCORED
    ]
    non_scored = [
        item
        for item in criterion_evaluations
        if item.status
        in {
            CriterionEvaluationStatus.NOT_APPLICABLE,
            CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
        }
    ]
    has_insufficient = any(
        item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
        for item in criterion_evaluations
    )
    has_not_applicable = any(
        item.status is CriterionEvaluationStatus.NOT_APPLICABLE for item in criterion_evaluations
    )
    has_human_review = any(item.human_review_required for item in criterion_evaluations)
    has_absence = any(item.absence_evidence is not None for item in criterion_evaluations)
    has_unknown_material_participation = any(
        any(span.speaker_role is SpeakerRole.UNKNOWN for span in item.evidence_spans)
        or item.reason_code is CriterionEvaluationReason.SELLER_ROLE_UNRESOLVED
        or item.human_review_reason is HumanReviewReason.AMBIGUOUS_SPEAKER_ROLE
        for item in criterion_evaluations
    )
    all_scored = bool(criterion_evaluations) and len(scored) == len(criterion_evaluations)
    partial = bool(scored) and bool(non_scored)
    provider_warning = bool(warning_codes)

    _require_flag_match(
        condition=has_insufficient,
        flag=EvaluationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT,
        flags=flag_set,
        message="INSUFFICIENT_EVIDENCE_PRESENT must match criterion statuses",
    )
    _require_flag_match(
        condition=has_not_applicable,
        flag=EvaluationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT,
        flags=flag_set,
        message="NOT_APPLICABLE_CRITERIA_PRESENT must match criterion statuses",
    )
    _require_flag_match(
        condition=has_human_review,
        flag=EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
        flags=flag_set,
        message="HUMAN_REVIEW_REQUIRED must match criterion review requirements",
    )
    _require_flag_match(
        condition=has_absence,
        flag=EvaluationQualityFlag.ABSENCE_EVIDENCE_USED,
        flags=flag_set,
        message="ABSENCE_EVIDENCE_USED must match absence evidence usage",
    )
    _require_flag_match(
        condition=has_unknown_material_participation,
        flag=EvaluationQualityFlag.UNKNOWN_SPEAKER_ROLES_PRESENT,
        flags=flag_set,
        message="UNKNOWN_SPEAKER_ROLES_PRESENT must match material unknown-role participation",
    )
    _require_flag_match(
        condition=all_scored,
        flag=EvaluationQualityFlag.ALL_CRITERIA_SCORED,
        flags=flag_set,
        message="ALL_CRITERIA_SCORED must match criterion statuses",
    )
    _require_flag_match(
        condition=partial,
        flag=EvaluationQualityFlag.PARTIAL_EVALUATION,
        flags=flag_set,
        message="PARTIAL_EVALUATION must match mixed scored/non-scored statuses",
    )
    _require_flag_match(
        condition=provider_warning,
        flag=EvaluationQualityFlag.PROVIDER_WARNING,
        flags=flag_set,
        message="PROVIDER_WARNING must match provider warning code presence",
    )
    if (
        EvaluationQualityFlag.ALL_CRITERIA_SCORED in flag_set
        and EvaluationQualityFlag.PARTIAL_EVALUATION in flag_set
    ):
        raise InvalidEvaluationResponseError(
            "ALL_CRITERIA_SCORED and PARTIAL_EVALUATION must be mutually exclusive"
        )


def _require_flag_match(
    *,
    condition: bool,
    flag: EvaluationQualityFlag,
    flags: set[EvaluationQualityFlag],
    message: str,
) -> None:
    has_flag = flag in flags
    if condition != has_flag:
        raise InvalidEvaluationResponseError(message)
