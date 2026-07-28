"""Unit tests for deterministic speaker-role assignment engine."""

from __future__ import annotations

import pytest

from sales_call_agent.alignment.models import AlignmentResult
from sales_call_agent.speaker_identity.engine import assign_speaker_roles
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentConfig,
    RoleAssignmentQualityFlag,
    RoleAssignmentRequest,
    RoleAssignmentStatus,
    RoleDecisionReason,
    RoleEvidence,
    RoleEvidenceType,
    SpeakerRole,
)


def _evidence(
    *,
    evidence_id: str,
    speaker_label: str,
    evidence_type: RoleEvidenceType,
    suggested_role: SpeakerRole,
) -> RoleEvidence:
    return RoleEvidence(
        evidence_id=evidence_id,
        speaker_label=speaker_label,
        evidence_type=evidence_type,
        suggested_role=suggested_role,
    )


def test_authoritative_resolved_ignores_lower_strength_conflicts(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-20",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.CALL_OPENING_HEURISTIC,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
            _evidence(
                evidence_id="ev-10",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.OPERATOR_OVERRIDE,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
    )

    result = assign_speaker_roles(request)
    assignment = result.assignments[0]
    assert assignment.role is SpeakerRole.SELLER
    assert assignment.status is RoleAssignmentStatus.ASSIGNED
    assert assignment.reason_code is RoleDecisionReason.AUTHORITATIVE_EVIDENCE
    assert assignment.supporting_evidence_ids == ("ev-10",)
    assert assignment.conflicting_evidence_ids == ()


def test_strong_resolved_ignores_moderate_and_weak_conflicts(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-30",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.KNOWN_SELLER_SOURCE,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
            _evidence(
                evidence_id="ev-20",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.TALK_TIME_HEURISTIC,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
            _evidence(
                evidence_id="ev-10",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
    )

    result = assign_speaker_roles(request)
    assignment = result.assignments[0]
    assert assignment.role is SpeakerRole.SELLER
    assert assignment.reason_code is RoleDecisionReason.STRONG_EVIDENCE
    assert assignment.supporting_evidence_ids == ("ev-10",)
    assert assignment.conflicting_evidence_ids == ()


def test_only_top_level_ids_are_emitted_for_traceability(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-40",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.KNOWN_SELLER_SOURCE,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
            _evidence(
                evidence_id="ev-30",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.TURN_PATTERN_HEURISTIC,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
            _evidence(
                evidence_id="ev-20",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                suggested_role=SpeakerRole.SELLER,
            ),
            _evidence(
                evidence_id="ev-10",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.VOICE_IDENTITY_MATCH,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
    )

    result = assign_speaker_roles(request)
    assignment = result.assignments[0]
    assert assignment.supporting_evidence_ids == ("ev-10", "ev-20")
    assert assignment.conflicting_evidence_ids == ()


def test_evidence_order_does_not_change_decision_or_id_ordering(
    alignment_result: AlignmentResult,
) -> None:
    evidence_a = (
        _evidence(
            evidence_id="ev-2",
            speaker_label="SPEAKER_00",
            evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
            suggested_role=SpeakerRole.SELLER,
        ),
        _evidence(
            evidence_id="ev-1",
            speaker_label="SPEAKER_00",
            evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
            suggested_role=SpeakerRole.SELLER,
        ),
    )
    evidence_b = tuple(reversed(evidence_a))

    result_a = assign_speaker_roles(
        RoleAssignmentRequest(call_id="call-1", alignment=alignment_result, evidence=evidence_a)
    )
    result_b = assign_speaker_roles(
        RoleAssignmentRequest(call_id="call-1", alignment=alignment_result, evidence=evidence_b)
    )

    assert result_a.assignments[0] == result_b.assignments[0]
    assert result_a.assignments[0].supporting_evidence_ids == ("ev-1", "ev-2")


def test_heuristic_only_evidence_disabled_returns_unknown_with_empty_traceability(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-1",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.CALL_OPENING_HEURISTIC,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
        config=RoleAssignmentConfig(allow_heuristics=False),
    )
    result = assign_speaker_roles(request)
    assignment = result.assignments[0]
    assert assignment.status is RoleAssignmentStatus.UNKNOWN
    assert assignment.role is SpeakerRole.UNKNOWN
    assert assignment.reason_code is RoleDecisionReason.HEURISTICS_DISABLED
    assert assignment.supporting_evidence_ids == ()
    assert assignment.conflicting_evidence_ids == ()


def test_conflicting_top_level_authoritative_evidence(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-2",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.OPERATOR_OVERRIDE,
                suggested_role=SpeakerRole.SELLER,
            ),
            _evidence(
                evidence_id="ev-1",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.HUMAN_CONFIRMATION,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
        ),
    )
    result = assign_speaker_roles(request)
    assignment = result.assignments[0]
    assert assignment.role is SpeakerRole.UNKNOWN
    assert assignment.status is RoleAssignmentStatus.CONFLICTED
    assert assignment.reason_code is RoleDecisionReason.AUTHORITATIVE_CONFLICT
    assert assignment.supporting_evidence_ids == ()
    assert assignment.conflicting_evidence_ids == ("ev-1", "ev-2")


def test_assignment_order_matches_alignment_speaker_labels(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-2",
                speaker_label="SPEAKER_01",
                evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                suggested_role=SpeakerRole.CUSTOMER,
            ),
            _evidence(
                evidence_id="ev-1",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
    )
    result = assign_speaker_roles(request)
    assert (
        tuple(item.speaker_label for item in result.assignments) == alignment_result.speaker_labels
    )


def test_empty_alignment_behavior_without_evidence(
    empty_alignment_result: AlignmentResult,
) -> None:
    result = assign_speaker_roles(
        RoleAssignmentRequest(call_id="call-1", alignment=empty_alignment_result, evidence=())
    )
    assert result.assignments == ()
    assert RoleAssignmentQualityFlag.NO_SPEAKERS_PRESENT in result.quality_flags
    assert RoleAssignmentQualityFlag.NO_ROLE_EVIDENCE in result.quality_flags
    assert RoleAssignmentQualityFlag.EXPECTED_SELLER_COUNT_MISMATCH in result.quality_flags
    assert RoleAssignmentQualityFlag.EXPECTED_CUSTOMER_COUNT_MISMATCH in result.quality_flags


def test_empty_alignment_behavior_with_evidence_rejected(
    empty_alignment_result: AlignmentResult,
) -> None:
    from sales_call_agent.speaker_identity.exceptions import InvalidRoleAssignmentInputError

    with pytest.raises(InvalidRoleAssignmentInputError, match="absent"):
        RoleAssignmentRequest(
            call_id="call-1",
            alignment=empty_alignment_result,
            evidence=(
                _evidence(
                    evidence_id="ev-1",
                    speaker_label="SPEAKER_00",
                    evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                    suggested_role=SpeakerRole.SELLER,
                ),
            ),
        )


def test_expected_count_flags_are_quality_only_not_forced_assignments(
    alignment_result: AlignmentResult,
) -> None:
    request = RoleAssignmentRequest(
        call_id="call-1",
        alignment=alignment_result,
        evidence=(
            _evidence(
                evidence_id="ev-1",
                speaker_label="SPEAKER_00",
                evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                suggested_role=SpeakerRole.SELLER,
            ),
            _evidence(
                evidence_id="ev-2",
                speaker_label="SPEAKER_01",
                evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                suggested_role=SpeakerRole.SELLER,
            ),
        ),
    )
    result = assign_speaker_roles(request)
    assert all(current.role is SpeakerRole.SELLER for current in result.assignments)
    assert RoleAssignmentQualityFlag.EXPECTED_CUSTOMER_COUNT_MISMATCH in result.quality_flags
    assert RoleAssignmentQualityFlag.EXPECTED_SELLER_COUNT_MISMATCH in result.quality_flags


def test_no_complement_assignment_path_exists(alignment_result: AlignmentResult) -> None:
    result = assign_speaker_roles(
        RoleAssignmentRequest(
            call_id="call-1",
            alignment=alignment_result,
            evidence=(
                _evidence(
                    evidence_id="ev-1",
                    speaker_label="SPEAKER_00",
                    evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
                    suggested_role=SpeakerRole.SELLER,
                ),
            ),
        )
    )
    second = result.assignments[1]
    assert second.role is SpeakerRole.UNKNOWN
    assert second.reason_code is RoleDecisionReason.NO_EVIDENCE
