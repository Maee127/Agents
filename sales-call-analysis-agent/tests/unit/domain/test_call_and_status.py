"""Behavioral tests for the Call aggregate and CallProcessingStatus transitions."""

from typing import Any

import pytest

from sales_call_agent.domain import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    InvalidCallError,
    InvalidStatusTransitionError,
)

LEGAL_TRANSITIONS = [
    (CallProcessingStatus.RECEIVED, CallProcessingStatus.VALIDATED),
    (CallProcessingStatus.RECEIVED, CallProcessingStatus.REJECTED),
    (CallProcessingStatus.RECEIVED, CallProcessingStatus.FAILED),
    (CallProcessingStatus.VALIDATED, CallProcessingStatus.TRANSCRIBED),
    (CallProcessingStatus.VALIDATED, CallProcessingStatus.FAILED),
    (CallProcessingStatus.TRANSCRIBED, CallProcessingStatus.DIARIZED),
    (CallProcessingStatus.TRANSCRIBED, CallProcessingStatus.FAILED),
    (CallProcessingStatus.DIARIZED, CallProcessingStatus.ROLES_ASSIGNED),
    (CallProcessingStatus.DIARIZED, CallProcessingStatus.FAILED),
    (CallProcessingStatus.ROLES_ASSIGNED, CallProcessingStatus.EVALUATED),
    (CallProcessingStatus.ROLES_ASSIGNED, CallProcessingStatus.FAILED),
]

ILLEGAL_TRANSITIONS = [
    (CallProcessingStatus.RECEIVED, CallProcessingStatus.TRANSCRIBED),
    (CallProcessingStatus.RECEIVED, CallProcessingStatus.EVALUATED),
    (CallProcessingStatus.VALIDATED, CallProcessingStatus.REJECTED),
    (CallProcessingStatus.TRANSCRIBED, CallProcessingStatus.VALIDATED),
    (CallProcessingStatus.EVALUATED, CallProcessingStatus.FAILED),
    (CallProcessingStatus.REJECTED, CallProcessingStatus.VALIDATED),
    (CallProcessingStatus.FAILED, CallProcessingStatus.RECEIVED),
]

TERMINAL_STATUSES = {
    CallProcessingStatus.EVALUATED,
    CallProcessingStatus.REJECTED,
    CallProcessingStatus.FAILED,
}


@pytest.fixture
def call(metadata_kwargs: dict[str, Any], audio_kwargs: dict[str, Any]) -> Call:
    return Call(metadata=CallMetadata(**metadata_kwargs), audio=AudioAsset(**audio_kwargs))


def test_expected_status_members_in_pipeline_order() -> None:
    assert [status.value for status in CallProcessingStatus] == [
        "received",
        "validated",
        "transcribed",
        "diarized",
        "roles_assigned",
        "evaluated",
        "rejected",
        "failed",
    ]


@pytest.mark.parametrize("status", list(CallProcessingStatus))
def test_is_terminal_matches_expected_set(status: CallProcessingStatus) -> None:
    assert status.is_terminal is (status in TERMINAL_STATUSES)


@pytest.mark.parametrize(("from_status", "to_status"), LEGAL_TRANSITIONS)
def test_legal_transitions_are_allowed(
    from_status: CallProcessingStatus, to_status: CallProcessingStatus
) -> None:
    assert from_status.can_transition_to(to_status)


@pytest.mark.parametrize(("from_status", "to_status"), ILLEGAL_TRANSITIONS)
def test_illegal_transitions_are_denied(
    from_status: CallProcessingStatus, to_status: CallProcessingStatus
) -> None:
    assert not from_status.can_transition_to(to_status)


def test_call_defaults_to_received(call: Call) -> None:
    assert call.status is CallProcessingStatus.RECEIVED


def test_call_id_mirrors_metadata(call: Call) -> None:
    assert call.call_id == call.metadata.call_id == "call-0001"


def test_storage_path_mismatch_raises(
    metadata_kwargs: dict[str, Any], audio_kwargs: dict[str, Any]
) -> None:
    audio_kwargs["storage_path"] = "calls/other/2026-07-26/other.mp3"

    with pytest.raises(InvalidCallError, match="storage_path"):
        Call(metadata=CallMetadata(**metadata_kwargs), audio=AudioAsset(**audio_kwargs))


def test_audio_channels_mismatch_raises(
    metadata_kwargs: dict[str, Any], audio_kwargs: dict[str, Any]
) -> None:
    audio_kwargs["audio_channels"] = AudioChannels.STEREO

    with pytest.raises(InvalidCallError, match="audio_channels"):
        Call(metadata=CallMetadata(**metadata_kwargs), audio=AudioAsset(**audio_kwargs))


def test_rejects_raw_string_status(
    metadata_kwargs: dict[str, Any], audio_kwargs: dict[str, Any]
) -> None:
    with pytest.raises(InvalidCallError, match="status"):
        Call(
            metadata=CallMetadata(**metadata_kwargs),
            audio=AudioAsset(**audio_kwargs),
            status="received",  # type: ignore[arg-type]
        )


def test_advance_to_returns_new_instance_and_preserves_original(call: Call) -> None:
    advanced = call.advance_to(CallProcessingStatus.VALIDATED)

    assert advanced is not call
    assert advanced.status is CallProcessingStatus.VALIDATED
    assert call.status is CallProcessingStatus.RECEIVED


def test_advance_to_illegal_transition_raises_with_statuses(call: Call) -> None:
    with pytest.raises(InvalidStatusTransitionError) as excinfo:
        call.advance_to(CallProcessingStatus.EVALUATED)

    assert excinfo.value.from_status is CallProcessingStatus.RECEIVED
    assert excinfo.value.to_status is CallProcessingStatus.EVALUATED


def test_transition_error_message_contains_no_call_id_or_pii(
    call: Call, metadata_kwargs: dict[str, Any]
) -> None:
    with pytest.raises(InvalidStatusTransitionError) as excinfo:
        call.advance_to(CallProcessingStatus.EVALUATED)

    message = str(excinfo.value)
    assert "RECEIVED" in message
    assert "EVALUATED" in message
    assert "call-0001" not in message
    assert metadata_kwargs["seller_number"] not in message
    assert metadata_kwargs["counterparty_phone"] not in message


def test_advance_to_rejects_raw_string(call: Call) -> None:
    with pytest.raises(InvalidCallError, match="new_status"):
        call.advance_to("validated")  # type: ignore[arg-type]


def test_full_happy_path_reaches_terminal_evaluated(call: Call) -> None:
    for status in (
        CallProcessingStatus.VALIDATED,
        CallProcessingStatus.TRANSCRIBED,
        CallProcessingStatus.DIARIZED,
        CallProcessingStatus.ROLES_ASSIGNED,
        CallProcessingStatus.EVALUATED,
    ):
        call = call.advance_to(status)

    assert call.status is CallProcessingStatus.EVALUATED
    assert call.status.is_terminal
