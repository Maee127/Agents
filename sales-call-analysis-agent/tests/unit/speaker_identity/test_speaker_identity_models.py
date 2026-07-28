"""Unit tests for speaker-role assignment models and validation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from sales_call_agent.alignment.models import AlignmentResult
from sales_call_agent.speaker_identity.exceptions import (
    InvalidRoleAssignmentInputError,
    InvalidRoleAssignmentResultError,
    InvalidRoleEvidenceError,
    UnsupportedRoleAssignmentConfigurationError,
)
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentConfig,
    RoleAssignmentQualityFlag,
    RoleAssignmentRequest,
    RoleAssignmentResult,
    RoleAssignmentStatus,
    RoleDecisionReason,
    RoleEvidence,
    RoleEvidenceStrength,
    RoleEvidenceType,
    SpeakerRole,
    SpeakerRoleAssignment,
)


def _evidence(
    *,
    evidence_id: str = "ev-1",
    speaker_label: str = "SPEAKER_00",
    evidence_type: RoleEvidenceType = RoleEvidenceType.KNOWN_CHANNEL,
    suggested_role: SpeakerRole = SpeakerRole.SELLER,
) -> RoleEvidence:
    return RoleEvidence(
        evidence_id=evidence_id,
        speaker_label=speaker_label,
        evidence_type=evidence_type,
        suggested_role=suggested_role,
    )


def _assignment(
    *,
    speaker_label: str = "SPEAKER_00",
    role: SpeakerRole = SpeakerRole.SELLER,
    status: RoleAssignmentStatus = RoleAssignmentStatus.ASSIGNED,
    reason_code: RoleDecisionReason = RoleDecisionReason.STRONG_EVIDENCE,
    supporting_evidence_ids: tuple[str, ...] = ("ev-1",),
    conflicting_evidence_ids: tuple[str, ...] = (),
) -> SpeakerRoleAssignment:
    return SpeakerRoleAssignment(
        speaker_label=speaker_label,
        role=role,
        status=status,
        reason_code=reason_code,
        supporting_evidence_ids=supporting_evidence_ids,
        conflicting_evidence_ids=conflicting_evidence_ids,
    )


def test_config_has_only_expected_fields() -> None:
    assert {current.name for current in fields(RoleAssignmentConfig)} == {
        "expected_seller_count",
        "expected_customer_count",
        "allow_heuristics",
    }


@pytest.mark.parametrize("field_name", ["expected_seller_count", "expected_customer_count"])
def test_config_rejects_negative_counts(field_name: str) -> None:
    with pytest.raises(UnsupportedRoleAssignmentConfigurationError):
        if field_name == "expected_seller_count":
            RoleAssignmentConfig(expected_seller_count=-1)
        else:
            RoleAssignmentConfig(expected_customer_count=-1)


def test_config_is_frozen() -> None:
    config = RoleAssignmentConfig()
    with pytest.raises(FrozenInstanceError):
        config.allow_heuristics = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("evidence_type", "strength"),
    [
        (RoleEvidenceType.OPERATOR_OVERRIDE, RoleEvidenceStrength.AUTHORITATIVE),
        (RoleEvidenceType.HUMAN_CONFIRMATION, RoleEvidenceStrength.AUTHORITATIVE),
        (RoleEvidenceType.VOICE_IDENTITY_MATCH, RoleEvidenceStrength.STRONG),
        (RoleEvidenceType.KNOWN_CHANNEL, RoleEvidenceStrength.STRONG),
        (RoleEvidenceType.KNOWN_SELLER_SOURCE, RoleEvidenceStrength.MODERATE),
        (RoleEvidenceType.CALL_OPENING_HEURISTIC, RoleEvidenceStrength.WEAK),
        (RoleEvidenceType.TURN_PATTERN_HEURISTIC, RoleEvidenceStrength.WEAK),
        (RoleEvidenceType.TALK_TIME_HEURISTIC, RoleEvidenceStrength.WEAK),
    ],
)
def test_evidence_strength_mapping_is_exact(
    evidence_type: RoleEvidenceType, strength: RoleEvidenceStrength
) -> None:
    assert _evidence(evidence_type=evidence_type).strength is strength


def test_evidence_requires_speaker_label() -> None:
    with pytest.raises(InvalidRoleEvidenceError):
        RoleEvidence(
            evidence_id="ev-1",
            speaker_label="",
            evidence_type=RoleEvidenceType.KNOWN_CHANNEL,
            suggested_role=SpeakerRole.SELLER,
        )


def test_evidence_has_only_expected_fields() -> None:
    assert {current.name for current in fields(RoleEvidence)} == {
        "evidence_id",
        "speaker_label",
        "evidence_type",
        "suggested_role",
        "warning_codes",
    }


def test_request_uses_default_config_factory(alignment_result: AlignmentResult) -> None:
    request = RoleAssignmentRequest(call_id="call-1", alignment=alignment_result)
    assert request.config == RoleAssignmentConfig()


def test_request_rejects_absent_speaker_evidence(alignment_result: AlignmentResult) -> None:
    with pytest.raises(InvalidRoleAssignmentInputError, match="absent"):
        RoleAssignmentRequest(
            call_id="call-1",
            alignment=alignment_result,
            evidence=(_evidence(speaker_label="SPEAKER_99"),),
        )


def test_request_repr_hides_alignment_text(alignment_result: AlignmentResult) -> None:
    request = RoleAssignmentRequest(call_id="call-1", alignment=alignment_result)
    rendered = repr(request)
    assert "SECRET_TRANSCRIPT_TOKEN_A" not in rendered
    assert "SECRET_TRANSCRIPT_TOKEN_B" not in rendered


def test_assignment_traceability_rules() -> None:
    with pytest.raises(InvalidRoleAssignmentResultError, match="requires supporting"):
        _assignment(supporting_evidence_ids=())
    with pytest.raises(InvalidRoleAssignmentResultError, match="requires empty supporting"):
        _assignment(
            role=SpeakerRole.UNKNOWN,
            status=RoleAssignmentStatus.CONFLICTED,
            reason_code=RoleDecisionReason.CONFLICTING_TOP_STRENGTH_EVIDENCE,
            supporting_evidence_ids=("ev-1",),
            conflicting_evidence_ids=("ev-2",),
        )
    with pytest.raises(InvalidRoleAssignmentResultError, match="requires empty evidence"):
        _assignment(
            role=SpeakerRole.UNKNOWN,
            status=RoleAssignmentStatus.UNKNOWN,
            reason_code=RoleDecisionReason.NO_EVIDENCE,
            supporting_evidence_ids=("ev-1",),
        )


def test_result_validates_quality_flags_from_assignment_facts() -> None:
    assignment = _assignment(
        speaker_label="SPEAKER_00",
        role=SpeakerRole.UNKNOWN,
        status=RoleAssignmentStatus.CONFLICTED,
        reason_code=RoleDecisionReason.AUTHORITATIVE_CONFLICT,
        supporting_evidence_ids=(),
        conflicting_evidence_ids=("ev-1", "ev-2"),
    )
    with pytest.raises(InvalidRoleAssignmentResultError, match="UNKNOWN_ROLES_PRESENT"):
        RoleAssignmentResult(
            call_id="call-1",
            assignments=(assignment,),
            quality_flags=(
                RoleAssignmentQualityFlag.CONFLICTING_EVIDENCE_PRESENT,
                RoleAssignmentQualityFlag.AUTHORITATIVE_CONFLICT_PRESENT,
                RoleAssignmentQualityFlag.SINGLE_SPEAKER_CALL,
            ),
        )


def test_result_allows_engine_only_flags_not_reconstructable() -> None:
    result = RoleAssignmentResult(
        call_id="call-1",
        assignments=(),
        quality_flags=(
            RoleAssignmentQualityFlag.NO_SPEAKERS_PRESENT,
            RoleAssignmentQualityFlag.NO_ROLE_EVIDENCE,
            RoleAssignmentQualityFlag.EXPECTED_SELLER_COUNT_MISMATCH,
            RoleAssignmentQualityFlag.EXPECTED_CUSTOMER_COUNT_MISMATCH,
        ),
    )
    assert result.assignments == ()
