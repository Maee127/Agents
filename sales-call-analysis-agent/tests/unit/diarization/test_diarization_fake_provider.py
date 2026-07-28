"""Unit tests for the deterministic fake diarization provider."""

from __future__ import annotations

import pytest

from sales_call_agent.diarization.exceptions import (
    DiarizationProviderUnavailableError,
    DiarizationRequestFailedError,
    DiarizationTimeoutError,
    InvalidDiarizationResponseError,
    UnsupportedSpeakerConstraintError,
)
from sales_call_agent.diarization.fake import (
    DeterministicFakeDiarizationProvider,
    FakeDiarizationFailureMode,
)
from sales_call_agent.diarization.models import DiarizationQualityFlag, DiarizationRequest
from sales_call_agent.diarization.provider import run_diarization


def _request(call_id: str = "call-1") -> DiarizationRequest:
    return DiarizationRequest(
        call_id=call_id,
        normalized_audio_path="normalized/test.asr.wav",
        normalized_audio_hash="abc123",
    )


def test_deterministic_output() -> None:
    provider = DeterministicFakeDiarizationProvider()
    first = run_diarization(provider, _request())
    second = run_diarization(provider, _request())
    assert first.turns == second.turns
    assert first.quality_flags == second.quality_flags


def test_two_speaker_alternating_turns() -> None:
    result = run_diarization(DeterministicFakeDiarizationProvider(), _request())
    assert result.speaker_count == 2
    assert len(result.turns) == 4
    assert result.turns[0].speaker_label == "SPEAKER_00"
    assert result.turns[1].speaker_label == "SPEAKER_01"


def test_single_speaker_result() -> None:
    provider = DeterministicFakeDiarizationProvider(single_speaker_call_ids=frozenset({"mono"}))
    result = run_diarization(provider, _request("mono"))
    assert result.speaker_count == 1
    assert DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED in result.quality_flags


def test_no_speech_result() -> None:
    provider = DeterministicFakeDiarizationProvider(no_speech_call_ids=frozenset({"silent"}))
    result = run_diarization(provider, _request("silent"))
    assert result.turns == ()
    assert result.speaker_count == 0
    assert DiarizationQualityFlag.NO_SPEECH_SEGMENTS in result.quality_flags


def test_overlapping_turns_preserved() -> None:
    provider = DeterministicFakeDiarizationProvider(overlapping_call_ids=frozenset({"overlap"}))
    result = run_diarization(provider, _request("overlap"))
    assert result.turns[0].end_seconds > result.turns[1].start_seconds
    assert DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED in result.quality_flags


def test_very_short_turns_flag_only_when_configured() -> None:
    provider = DeterministicFakeDiarizationProvider(very_short_turns_call_ids=frozenset({"short"}))
    result = run_diarization(provider, _request("short"))
    assert DiarizationQualityFlag.VERY_SHORT_TURNS_PRESENT in result.quality_flags

    default = run_diarization(DeterministicFakeDiarizationProvider(), _request())
    assert DiarizationQualityFlag.VERY_SHORT_TURNS_PRESENT not in default.quality_flags


@pytest.mark.parametrize(
    ("mode", "exception_type"),
    [
        (FakeDiarizationFailureMode.PROVIDER_UNAVAILABLE, DiarizationProviderUnavailableError),
        (FakeDiarizationFailureMode.TIMEOUT, DiarizationTimeoutError),
        (FakeDiarizationFailureMode.REQUEST_FAILED, DiarizationRequestFailedError),
        (FakeDiarizationFailureMode.UNSUPPORTED_CONSTRAINT, UnsupportedSpeakerConstraintError),
    ],
)
def test_failure_modes_raise_exact_categories(
    mode: FakeDiarizationFailureMode,
    exception_type: type[Exception],
) -> None:
    provider = DeterministicFakeDiarizationProvider(
        failure_modes_by_call_id={"fail": mode},
    )
    with pytest.raises(exception_type):
        run_diarization(provider, _request("fail"))


def test_invalid_fake_response_maps_to_invalid_response() -> None:
    provider = DeterministicFakeDiarizationProvider(
        failure_modes_by_call_id={"bad": FakeDiarizationFailureMode.INVALID_RESPONSE},
    )
    with pytest.raises(InvalidDiarizationResponseError):
        run_diarization(provider, _request("bad"))


def test_external_mutation_of_configuration_does_not_alter_behavior() -> None:
    modes = {"stable": FakeDiarizationFailureMode.REQUEST_FAILED}
    provider = DeterministicFakeDiarizationProvider(failure_modes_by_call_id=modes)
    modes["stable"] = FakeDiarizationFailureMode.TIMEOUT
    modes["new"] = FakeDiarizationFailureMode.TIMEOUT

    with pytest.raises(DiarizationRequestFailedError):
        run_diarization(provider, _request("stable"))

    with pytest.raises(DiarizationProviderUnavailableError):
        run_diarization(
            DeterministicFakeDiarizationProvider(
                failure_modes_by_call_id={"stable": FakeDiarizationFailureMode.PROVIDER_UNAVAILABLE}
            ),
            _request("stable"),
        )
