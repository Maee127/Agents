"""Unit tests for the diarization provider protocol and run helper."""

from __future__ import annotations

import pytest

from sales_call_agent.diarization.exceptions import (
    DiarizationProviderUnavailableError,
    InvalidDiarizationInputError,
    InvalidDiarizationResponseError,
)
from sales_call_agent.diarization.fake import (
    DeterministicFakeDiarizationProvider,
    FakeDiarizationFailureMode,
)
from sales_call_agent.diarization.models import (
    DiarizationQualityFlag,
    DiarizationRequest,
    DiarizationResult,
    SpeakerTurn,
)
from sales_call_agent.diarization.provider import DiarizationProvider, run_diarization


class _MismatchProvider:
    provider_name = "fake"
    model_name = "fake_v1"

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        return DiarizationResult(
            call_id="other-call",
            turns=(),
            provider_name=self.provider_name,
            model_name=self.model_name,
            quality_flags=(DiarizationQualityFlag.NO_SPEECH_SEGMENTS,),
        )


class _ExactCountMismatchProvider:
    provider_name = "fake"
    model_name = "fake_v1"

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        turns = (
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
        )
        return DiarizationResult(
            call_id=request.call_id,
            turns=turns,
            provider_name=self.provider_name,
            model_name=self.model_name,
            quality_flags=(),
        )


def test_provider_structural_conformance(sample_request: DiarizationRequest) -> None:
    provider: DiarizationProvider = DeterministicFakeDiarizationProvider()
    result = run_diarization(provider, sample_request)
    assert result.call_id == sample_request.call_id
    assert result.provider_name == provider.provider_name
    assert result.model_name == provider.model_name
    assert result.turns


def test_run_diarization_identity_checks(sample_request: DiarizationRequest) -> None:
    provider = DeterministicFakeDiarizationProvider()
    result = run_diarization(provider, sample_request)
    assert result.call_id == sample_request.call_id
    assert result.provider_name == provider.provider_name
    assert result.model_name == provider.model_name


def test_invalid_request_type_rejected() -> None:
    provider = DeterministicFakeDiarizationProvider()
    with pytest.raises(InvalidDiarizationInputError, match="DiarizationRequest"):
        run_diarization(provider, object())  # type: ignore[arg-type]


def test_mismatched_call_id_rejected(sample_request: DiarizationRequest) -> None:
    with pytest.raises(InvalidDiarizationResponseError, match="call_id"):
        run_diarization(_MismatchProvider(), sample_request)


def test_known_diarization_error_propagates(sample_request: DiarizationRequest) -> None:
    provider = DeterministicFakeDiarizationProvider(
        failure_modes_by_call_id={
            sample_request.call_id: FakeDiarizationFailureMode.PROVIDER_UNAVAILABLE
        },
    )
    with pytest.raises(DiarizationProviderUnavailableError):
        run_diarization(provider, sample_request)


def test_programming_error_not_wrapped(sample_request: DiarizationRequest) -> None:
    class _BuggyProvider:
        provider_name = "fake"
        model_name = "fake_v1"

        def diarize(self, request: DiarizationRequest) -> DiarizationResult:
            raise KeyError("unexpected-bug")

    with pytest.raises(KeyError, match="unexpected-bug"):
        run_diarization(_BuggyProvider(), sample_request)


def test_exact_speaker_count_mismatch_rejected(sample_request: DiarizationRequest) -> None:
    request = DiarizationRequest(
        call_id=sample_request.call_id,
        normalized_audio_path=sample_request.normalized_audio_path,
        normalized_audio_hash=sample_request.normalized_audio_hash,
        exact_expected_speakers=1,
    )
    with pytest.raises(InvalidDiarizationResponseError, match="exact expected speaker count"):
        run_diarization(_ExactCountMismatchProvider(), request)


def test_min_max_hints_do_not_mutate_result(sample_request: DiarizationRequest) -> None:
    request = DiarizationRequest(
        call_id=sample_request.call_id,
        normalized_audio_path=sample_request.normalized_audio_path,
        normalized_audio_hash=sample_request.normalized_audio_hash,
        min_expected_speakers=3,
        max_expected_speakers=4,
    )
    provider = DeterministicFakeDiarizationProvider()
    result = run_diarization(provider, request)
    assert result.speaker_count == 2
    assert DiarizationQualityFlag.SPEAKER_COUNT_UNCERTAIN not in result.quality_flags
