"""Provider-independent models for speaker-role assignment."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from sales_call_agent.alignment.models import AlignmentResult
from sales_call_agent.speaker_identity.exceptions import (
    InvalidRoleAssignmentInputError,
    InvalidRoleAssignmentResultError,
    InvalidRoleEvidenceError,
    UnsupportedRoleAssignmentConfigurationError,
)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SPEAKER_LABEL_RE = re.compile(r"^SPEAKER_[0-9]{2,}$")


class SpeakerRole(StrEnum):
    """Business role assigned to an anonymous speaker label."""

    SELLER = "seller"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


class RoleAssignmentStatus(StrEnum):
    """Assignment outcome for one speaker label."""

    ASSIGNED = "assigned"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"


class RoleEvidenceType(StrEnum):
    """Closed set of accepted role-evidence categories."""

    OPERATOR_OVERRIDE = "operator_override"
    HUMAN_CONFIRMATION = "human_confirmation"
    VOICE_IDENTITY_MATCH = "voice_identity_match"
    KNOWN_CHANNEL = "known_channel"
    KNOWN_SELLER_SOURCE = "known_seller_source"
    CALL_OPENING_HEURISTIC = "call_opening_heuristic"
    TURN_PATTERN_HEURISTIC = "turn_pattern_heuristic"
    TALK_TIME_HEURISTIC = "talk_time_heuristic"


class RoleEvidenceStrength(StrEnum):
    """Derived precedence level used by role decision rules."""

    AUTHORITATIVE = "authoritative"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class RoleDecisionReason(StrEnum):
    """Closed reason codes for role decisions."""

    AUTHORITATIVE_EVIDENCE = "authoritative_evidence"
    STRONG_EVIDENCE = "strong_evidence"
    MODERATE_EVIDENCE = "moderate_evidence"
    WEAK_HEURISTIC = "weak_heuristic"
    NO_EVIDENCE = "no_evidence"
    HEURISTICS_DISABLED = "heuristics_disabled"
    CONFLICTING_TOP_STRENGTH_EVIDENCE = "conflicting_top_strength_evidence"
    AUTHORITATIVE_CONFLICT = "authoritative_conflict"


class RoleAssignmentQualityFlag(StrEnum):
    """Quality/completeness conditions for role assignment outputs."""

    NO_ROLE_EVIDENCE = "no_role_evidence"
    UNKNOWN_ROLES_PRESENT = "unknown_roles_present"
    CONFLICTING_EVIDENCE_PRESENT = "conflicting_evidence_present"
    AUTHORITATIVE_CONFLICT_PRESENT = "authoritative_conflict_present"
    EXPECTED_SELLER_COUNT_MISMATCH = "expected_seller_count_mismatch"
    EXPECTED_CUSTOMER_COUNT_MISMATCH = "expected_customer_count_mismatch"
    HEURISTIC_EVIDENCE_USED = "heuristic_evidence_used"
    MULTI_PARTY_CALL = "multi_party_call"
    SINGLE_SPEAKER_CALL = "single_speaker_call"
    PARTIAL_ROLE_ASSIGNMENT = "partial_role_assignment"
    NO_SPEAKERS_PRESENT = "no_speakers_present"


def _ensure_required_string(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")


def _ensure_enum_member(
    value: object, enum_type: type[Enum], field_name: str, error: type[Exception]
) -> None:
    if not isinstance(value, enum_type):
        raise error(f"{field_name} must be a {enum_type.__name__} member")


def _ensure_non_negative_count(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnsupportedRoleAssignmentConfigurationError(f"{field_name} must be an integer")
    if value < 0:
        raise UnsupportedRoleAssignmentConfigurationError(f"{field_name} must not be negative")


def _ensure_safe_warning_code(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not value.strip():
        raise error(f"{field_name} must not be empty or whitespace-only")
    if not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise error(f"{field_name} must be a safe warning code")


def _ensure_speaker_label(value: object, field_name: str, error: type[Exception]) -> None:
    if not isinstance(value, str):
        raise error(f"{field_name} must be a string")
    if not _SPEAKER_LABEL_RE.fullmatch(value):
        raise error(f"{field_name} must match the canonical speaker label format")


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleAssignmentConfig:
    """Stable deterministic configuration for speaker-role assignment."""

    expected_seller_count: int | None = 1
    expected_customer_count: int | None = 1
    allow_heuristics: bool = False

    def __post_init__(self) -> None:
        if self.expected_seller_count is not None:
            _ensure_non_negative_count(self.expected_seller_count, "expected_seller_count")
        if self.expected_customer_count is not None:
            _ensure_non_negative_count(self.expected_customer_count, "expected_customer_count")
        if not isinstance(self.allow_heuristics, bool):
            raise UnsupportedRoleAssignmentConfigurationError("allow_heuristics must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleEvidence:
    """One speaker-scoped evidence item for role-assignment decisions."""

    evidence_id: str
    speaker_label: str
    evidence_type: RoleEvidenceType
    suggested_role: SpeakerRole
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.evidence_id, "evidence_id", InvalidRoleEvidenceError)
        _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidRoleEvidenceError)
        _ensure_enum_member(
            self.evidence_type, RoleEvidenceType, "evidence_type", InvalidRoleEvidenceError
        )
        _ensure_enum_member(
            self.suggested_role, SpeakerRole, "suggested_role", InvalidRoleEvidenceError
        )
        if self.suggested_role is SpeakerRole.UNKNOWN:
            raise InvalidRoleEvidenceError(
                "suggested_role must be SELLER or CUSTOMER for role evidence"
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidRoleEvidenceError)

    @property
    def strength(self) -> RoleEvidenceStrength:
        """Derived precedence strength from evidence type."""
        if self.evidence_type in (
            RoleEvidenceType.OPERATOR_OVERRIDE,
            RoleEvidenceType.HUMAN_CONFIRMATION,
        ):
            return RoleEvidenceStrength.AUTHORITATIVE
        if self.evidence_type in (
            RoleEvidenceType.VOICE_IDENTITY_MATCH,
            RoleEvidenceType.KNOWN_CHANNEL,
        ):
            return RoleEvidenceStrength.STRONG
        if self.evidence_type is RoleEvidenceType.KNOWN_SELLER_SOURCE:
            return RoleEvidenceStrength.MODERATE
        return RoleEvidenceStrength.WEAK


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleAssignmentRequest:
    """Input contract for deterministic speaker-role assignment."""

    call_id: str
    alignment: AlignmentResult = field(repr=False)
    evidence: tuple[RoleEvidence, ...] = ()
    config: RoleAssignmentConfig = field(default_factory=RoleAssignmentConfig)

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidRoleAssignmentInputError)
        if not isinstance(self.alignment, AlignmentResult):
            raise InvalidRoleAssignmentInputError("alignment must be an AlignmentResult")
        if self.alignment.call_id != self.call_id:
            raise InvalidRoleAssignmentInputError(
                "alignment call_id does not match request call_id"
            )
        if not isinstance(self.config, RoleAssignmentConfig):
            raise InvalidRoleAssignmentInputError("config must be a RoleAssignmentConfig")

        speaker_labels = set(self.alignment.speaker_labels)
        seen_ids: set[str] = set()
        for evidence in self.evidence:
            if not isinstance(evidence, RoleEvidence):
                raise InvalidRoleAssignmentInputError("evidence must contain RoleEvidence values")
            if evidence.evidence_id in seen_ids:
                raise InvalidRoleEvidenceError("evidence_id values must be unique")
            seen_ids.add(evidence.evidence_id)
            if evidence.speaker_label not in speaker_labels:
                raise InvalidRoleAssignmentInputError(
                    "role evidence references a speaker label absent from alignment"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeakerRoleAssignment:
    """Role assignment decision for one canonical speaker label."""

    speaker_label: str
    role: SpeakerRole
    status: RoleAssignmentStatus
    reason_code: RoleDecisionReason
    supporting_evidence_ids: tuple[str, ...] = ()
    conflicting_evidence_ids: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_speaker_label(self.speaker_label, "speaker_label", InvalidRoleAssignmentResultError)
        _ensure_enum_member(self.role, SpeakerRole, "role", InvalidRoleAssignmentResultError)
        _ensure_enum_member(
            self.status, RoleAssignmentStatus, "status", InvalidRoleAssignmentResultError
        )
        _ensure_enum_member(
            self.reason_code, RoleDecisionReason, "reason_code", InvalidRoleAssignmentResultError
        )

        if self.status is RoleAssignmentStatus.ASSIGNED:
            if self.role is SpeakerRole.UNKNOWN:
                raise InvalidRoleAssignmentResultError(
                    "assigned status requires seller or customer role"
                )
        else:
            if self.role is not SpeakerRole.UNKNOWN:
                raise InvalidRoleAssignmentResultError(
                    "unknown/conflicted status requires UNKNOWN role"
                )

        _validate_id_tuple(
            self.supporting_evidence_ids,
            "supporting_evidence_ids",
            InvalidRoleAssignmentResultError,
        )
        _validate_id_tuple(
            self.conflicting_evidence_ids,
            "conflicting_evidence_ids",
            InvalidRoleAssignmentResultError,
        )
        overlap = set(self.supporting_evidence_ids) & set(self.conflicting_evidence_ids)
        if overlap:
            raise InvalidRoleAssignmentResultError(
                "supporting and conflicting evidence IDs must not overlap"
            )

        if self.status is RoleAssignmentStatus.ASSIGNED:
            if not self.supporting_evidence_ids:
                raise InvalidRoleAssignmentResultError(
                    "assigned status requires supporting evidence IDs"
                )
            if self.conflicting_evidence_ids:
                raise InvalidRoleAssignmentResultError(
                    "assigned status must not include conflicting evidence IDs"
                )
        elif self.status is RoleAssignmentStatus.CONFLICTED:
            if self.supporting_evidence_ids:
                raise InvalidRoleAssignmentResultError(
                    "conflicted status requires empty supporting evidence IDs"
                )
            if not self.conflicting_evidence_ids:
                raise InvalidRoleAssignmentResultError(
                    "conflicted status requires conflicting evidence IDs"
                )
        elif self.status is RoleAssignmentStatus.UNKNOWN:
            if self.supporting_evidence_ids or self.conflicting_evidence_ids:
                raise InvalidRoleAssignmentResultError(
                    "unknown status requires empty evidence traceability IDs"
                )

        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidRoleAssignmentResultError)


@dataclass(frozen=True, slots=True, kw_only=True)
class RoleAssignmentResult:
    """Speaker-role assignment output for one call."""

    call_id: str
    assignments: tuple[SpeakerRoleAssignment, ...]
    quality_flags: tuple[RoleAssignmentQualityFlag, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ensure_required_string(self.call_id, "call_id", InvalidRoleAssignmentResultError)

        seen_labels: set[str] = set()
        for assignment in self.assignments:
            if not isinstance(assignment, SpeakerRoleAssignment):
                raise InvalidRoleAssignmentResultError(
                    "assignments must contain SpeakerRoleAssignment values"
                )
            if assignment.speaker_label in seen_labels:
                raise InvalidRoleAssignmentResultError("assignment speaker labels must be unique")
            seen_labels.add(assignment.speaker_label)

        for flag in self.quality_flags:
            _ensure_enum_member(
                flag,
                RoleAssignmentQualityFlag,
                "quality_flags",
                InvalidRoleAssignmentResultError,
            )
        for code in self.warning_codes:
            _ensure_safe_warning_code(code, "warning_codes", InvalidRoleAssignmentResultError)

        _validate_quality_flag_consistency(self.assignments, self.quality_flags)

    @property
    def seller_speaker_labels(self) -> tuple[str, ...]:
        return tuple(
            assignment.speaker_label
            for assignment in self.assignments
            if assignment.role is SpeakerRole.SELLER
        )

    @property
    def customer_speaker_labels(self) -> tuple[str, ...]:
        return tuple(
            assignment.speaker_label
            for assignment in self.assignments
            if assignment.role is SpeakerRole.CUSTOMER
        )

    @property
    def unknown_speaker_labels(self) -> tuple[str, ...]:
        return tuple(
            assignment.speaker_label
            for assignment in self.assignments
            if assignment.role is SpeakerRole.UNKNOWN
        )

    @property
    def has_exactly_one_seller(self) -> bool:
        return len(self.seller_speaker_labels) == 1

    @property
    def has_exactly_one_customer(self) -> bool:
        return len(self.customer_speaker_labels) == 1


def _validate_id_tuple(
    values: Sequence[str],
    field_name: str,
    error: type[Exception],
) -> None:
    previous: str | None = None
    seen: set[str] = set()
    for value in values:
        _ensure_required_string(value, field_name, error)
        if value in seen:
            raise error(f"{field_name} values must be unique")
        seen.add(value)
        if previous is not None and value < previous:
            raise error(f"{field_name} values must be deterministically ordered")
        previous = value


def _validate_quality_flag_consistency(
    assignments: Sequence[SpeakerRoleAssignment],
    quality_flags: Sequence[RoleAssignmentQualityFlag],
) -> None:
    flag_set = set(quality_flags)
    speaker_count = len(assignments)
    unknown_present = any(assignment.role is SpeakerRole.UNKNOWN for assignment in assignments)
    conflicted_present = any(
        assignment.status is RoleAssignmentStatus.CONFLICTED for assignment in assignments
    )
    authoritative_conflict_present = any(
        assignment.reason_code is RoleDecisionReason.AUTHORITATIVE_CONFLICT
        for assignment in assignments
    )
    heuristic_used = any(
        assignment.reason_code is RoleDecisionReason.WEAK_HEURISTIC
        and assignment.status is RoleAssignmentStatus.ASSIGNED
        for assignment in assignments
    )
    assigned_count = sum(
        1 for assignment in assignments if assignment.status is RoleAssignmentStatus.ASSIGNED
    )
    unresolved_count = sum(
        1
        for assignment in assignments
        if assignment.status in {RoleAssignmentStatus.UNKNOWN, RoleAssignmentStatus.CONFLICTED}
    )
    partial_present = assigned_count > 0 and unresolved_count > 0

    _require_flag_match(
        condition=speaker_count == 0,
        flag=RoleAssignmentQualityFlag.NO_SPEAKERS_PRESENT,
        flags=flag_set,
        message="NO_SPEAKERS_PRESENT must match assignment emptiness",
    )
    _require_flag_match(
        condition=speaker_count == 1,
        flag=RoleAssignmentQualityFlag.SINGLE_SPEAKER_CALL,
        flags=flag_set,
        message="SINGLE_SPEAKER_CALL must match speaker count",
    )
    _require_flag_match(
        condition=speaker_count > 1,
        flag=RoleAssignmentQualityFlag.MULTI_PARTY_CALL,
        flags=flag_set,
        message="MULTI_PARTY_CALL must match speaker count",
    )
    _require_flag_match(
        condition=unknown_present,
        flag=RoleAssignmentQualityFlag.UNKNOWN_ROLES_PRESENT,
        flags=flag_set,
        message="UNKNOWN_ROLES_PRESENT must match unknown role presence",
    )
    _require_flag_match(
        condition=conflicted_present,
        flag=RoleAssignmentQualityFlag.CONFLICTING_EVIDENCE_PRESENT,
        flags=flag_set,
        message="CONFLICTING_EVIDENCE_PRESENT must match conflicted assignment presence",
    )
    _require_flag_match(
        condition=authoritative_conflict_present,
        flag=RoleAssignmentQualityFlag.AUTHORITATIVE_CONFLICT_PRESENT,
        flags=flag_set,
        message="AUTHORITATIVE_CONFLICT_PRESENT must match authoritative conflicts",
    )
    _require_flag_match(
        condition=heuristic_used,
        flag=RoleAssignmentQualityFlag.HEURISTIC_EVIDENCE_USED,
        flags=flag_set,
        message="HEURISTIC_EVIDENCE_USED must match heuristic assignment usage",
    )
    _require_flag_match(
        condition=partial_present,
        flag=RoleAssignmentQualityFlag.PARTIAL_ROLE_ASSIGNMENT,
        flags=flag_set,
        message="PARTIAL_ROLE_ASSIGNMENT must follow its exact consistency rule",
    )


def _require_flag_match(
    *,
    condition: bool,
    flag: RoleAssignmentQualityFlag,
    flags: set[RoleAssignmentQualityFlag],
    message: str,
) -> None:
    has_flag = flag in flags
    if condition != has_flag:
        raise InvalidRoleAssignmentResultError(message)
