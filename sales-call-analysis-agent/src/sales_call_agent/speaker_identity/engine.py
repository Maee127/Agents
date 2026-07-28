"""Deterministic engine mapping anonymous speakers to business roles."""

from __future__ import annotations

from collections.abc import Sequence

from sales_call_agent.speaker_identity.models import (
    RoleAssignmentConfig,
    RoleAssignmentQualityFlag,
    RoleAssignmentRequest,
    RoleAssignmentResult,
    RoleAssignmentStatus,
    RoleDecisionReason,
    RoleEvidence,
    RoleEvidenceStrength,
    SpeakerRole,
    SpeakerRoleAssignment,
)

_STRENGTH_PRECEDENCE: tuple[RoleEvidenceStrength, ...] = (
    RoleEvidenceStrength.AUTHORITATIVE,
    RoleEvidenceStrength.STRONG,
    RoleEvidenceStrength.MODERATE,
    RoleEvidenceStrength.WEAK,
)


def assign_speaker_roles(request: RoleAssignmentRequest) -> RoleAssignmentResult:
    """Assign roles per aligned speaker with deterministic precedence rules."""
    by_speaker = _group_evidence_by_speaker(request.evidence)
    assignments: list[SpeakerRoleAssignment] = []

    for speaker_label in request.alignment.speaker_labels:
        speaker_evidence = by_speaker.get(speaker_label, ())
        assignment = _resolve_assignment_for_speaker(
            speaker_label=speaker_label,
            evidence=speaker_evidence,
            config=request.config,
        )
        assignments.append(assignment)

    quality_flags = _derive_quality_flags(
        assignments=assignments,
        evidence=request.evidence,
        config=request.config,
    )
    return RoleAssignmentResult(
        call_id=request.call_id,
        assignments=tuple(assignments),
        quality_flags=tuple(sorted(quality_flags, key=lambda flag: flag.value)),
    )


def _group_evidence_by_speaker(
    evidence_items: Sequence[RoleEvidence],
) -> dict[str, tuple[RoleEvidence, ...]]:
    grouped: dict[str, list[RoleEvidence]] = {}
    for evidence in evidence_items:
        grouped.setdefault(evidence.speaker_label, []).append(evidence)
    return {
        speaker_label: tuple(sorted(items, key=lambda item: item.evidence_id))
        for speaker_label, items in grouped.items()
    }


def _resolve_assignment_for_speaker(
    *,
    speaker_label: str,
    evidence: Sequence[RoleEvidence],
    config: RoleAssignmentConfig,
) -> SpeakerRoleAssignment:
    if not evidence:
        return SpeakerRoleAssignment(
            speaker_label=speaker_label,
            role=SpeakerRole.UNKNOWN,
            status=RoleAssignmentStatus.UNKNOWN,
            reason_code=RoleDecisionReason.NO_EVIDENCE,
        )

    evidence_by_strength = _partition_by_strength(evidence)
    top_strength = _select_top_strength(evidence_by_strength)
    if top_strength is None:
        return SpeakerRoleAssignment(
            speaker_label=speaker_label,
            role=SpeakerRole.UNKNOWN,
            status=RoleAssignmentStatus.UNKNOWN,
            reason_code=RoleDecisionReason.NO_EVIDENCE,
        )

    top_level_items = evidence_by_strength[top_strength]
    if top_strength is RoleEvidenceStrength.WEAK and not config.allow_heuristics:
        return SpeakerRoleAssignment(
            speaker_label=speaker_label,
            role=SpeakerRole.UNKNOWN,
            status=RoleAssignmentStatus.UNKNOWN,
            reason_code=RoleDecisionReason.HEURISTICS_DISABLED,
        )

    roles_in_top = {item.suggested_role for item in top_level_items}
    if len(roles_in_top) == 1:
        selected_role = next(iter(roles_in_top))
        return SpeakerRoleAssignment(
            speaker_label=speaker_label,
            role=selected_role,
            status=RoleAssignmentStatus.ASSIGNED,
            reason_code=_reason_for_resolved_strength(top_strength),
            supporting_evidence_ids=tuple(
                sorted(
                    item.evidence_id
                    for item in top_level_items
                    if item.suggested_role is selected_role
                )
            ),
        )

    return SpeakerRoleAssignment(
        speaker_label=speaker_label,
        role=SpeakerRole.UNKNOWN,
        status=RoleAssignmentStatus.CONFLICTED,
        reason_code=(
            RoleDecisionReason.AUTHORITATIVE_CONFLICT
            if top_strength is RoleEvidenceStrength.AUTHORITATIVE
            else RoleDecisionReason.CONFLICTING_TOP_STRENGTH_EVIDENCE
        ),
        conflicting_evidence_ids=tuple(sorted(item.evidence_id for item in top_level_items)),
    )


def _partition_by_strength(
    evidence: Sequence[RoleEvidence],
) -> dict[RoleEvidenceStrength, tuple[RoleEvidence, ...]]:
    grouped: dict[RoleEvidenceStrength, list[RoleEvidence]] = {}
    for item in evidence:
        grouped.setdefault(item.strength, []).append(item)
    return {
        strength: tuple(sorted(items, key=lambda current: current.evidence_id))
        for strength, items in grouped.items()
    }


def _select_top_strength(
    evidence_by_strength: dict[RoleEvidenceStrength, tuple[RoleEvidence, ...]],
) -> RoleEvidenceStrength | None:
    for strength in _STRENGTH_PRECEDENCE:
        if evidence_by_strength.get(strength):
            return strength
    return None


def _reason_for_resolved_strength(strength: RoleEvidenceStrength) -> RoleDecisionReason:
    if strength is RoleEvidenceStrength.AUTHORITATIVE:
        return RoleDecisionReason.AUTHORITATIVE_EVIDENCE
    if strength is RoleEvidenceStrength.STRONG:
        return RoleDecisionReason.STRONG_EVIDENCE
    if strength is RoleEvidenceStrength.MODERATE:
        return RoleDecisionReason.MODERATE_EVIDENCE
    return RoleDecisionReason.WEAK_HEURISTIC


def _derive_quality_flags(
    *,
    assignments: Sequence[SpeakerRoleAssignment],
    evidence: Sequence[RoleEvidence],
    config: RoleAssignmentConfig,
) -> set[RoleAssignmentQualityFlag]:
    flags: set[RoleAssignmentQualityFlag] = set()
    speaker_count = len(assignments)
    seller_count = sum(1 for item in assignments if item.role is SpeakerRole.SELLER)
    customer_count = sum(1 for item in assignments if item.role is SpeakerRole.CUSTOMER)
    unknown_count = sum(1 for item in assignments if item.role is SpeakerRole.UNKNOWN)
    conflicted_present = any(item.status is RoleAssignmentStatus.CONFLICTED for item in assignments)
    authoritative_conflict_present = any(
        item.reason_code is RoleDecisionReason.AUTHORITATIVE_CONFLICT for item in assignments
    )
    heuristic_assignment_present = any(
        item.status is RoleAssignmentStatus.ASSIGNED
        and item.reason_code is RoleDecisionReason.WEAK_HEURISTIC
        for item in assignments
    )

    if speaker_count == 0:
        flags.add(RoleAssignmentQualityFlag.NO_SPEAKERS_PRESENT)
    elif speaker_count == 1:
        flags.add(RoleAssignmentQualityFlag.SINGLE_SPEAKER_CALL)
    else:
        flags.add(RoleAssignmentQualityFlag.MULTI_PARTY_CALL)

    if unknown_count > 0:
        flags.add(RoleAssignmentQualityFlag.UNKNOWN_ROLES_PRESENT)
    if conflicted_present:
        flags.add(RoleAssignmentQualityFlag.CONFLICTING_EVIDENCE_PRESENT)
    if authoritative_conflict_present:
        flags.add(RoleAssignmentQualityFlag.AUTHORITATIVE_CONFLICT_PRESENT)
    if heuristic_assignment_present:
        flags.add(RoleAssignmentQualityFlag.HEURISTIC_EVIDENCE_USED)

    if (
        any(item.status is RoleAssignmentStatus.ASSIGNED for item in assignments)
        and unknown_count > 0
    ):
        flags.add(RoleAssignmentQualityFlag.PARTIAL_ROLE_ASSIGNMENT)

    if not evidence:
        flags.add(RoleAssignmentQualityFlag.NO_ROLE_EVIDENCE)

    if config.expected_seller_count is not None and seller_count != config.expected_seller_count:
        flags.add(RoleAssignmentQualityFlag.EXPECTED_SELLER_COUNT_MISMATCH)
    if (
        config.expected_customer_count is not None
        and customer_count != config.expected_customer_count
    ):
        flags.add(RoleAssignmentQualityFlag.EXPECTED_CUSTOMER_COUNT_MISMATCH)

    return flags
