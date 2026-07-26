"""Unit tests for deterministic fake transcription provider."""

from __future__ import annotations

import pytest

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionResponseError,
    TranscriptionProviderUnavailableError,
    TranscriptionRequestFailedError,
    TranscriptionTimeoutError,
    UnsupportedTranscriptionLanguageError,
)
from sales_call_agent.transcription.fake import (
    DeterministicFakeTranscriptionProvider,
    FakeFailureMode,
)
from sales_call_agent.transcription.models import TranscriptionQualityFlag
from sales_call_agent.transcription.provider import run_transcription


def test_fake_provider_is_deterministic(transcription_request) -> None:
    provider = DeterministicFakeTranscriptionProvider()
    first = run_transcription(provider, transcription_request)
    second = run_transcription(provider, transcription_request)
    assert first == second


def test_fake_provider_no_speech_result_is_valid(transcription_request) -> None:
    provider = DeterministicFakeTranscriptionProvider(
        no_speech_call_ids=frozenset({transcription_request.call_id})
    )
    result = run_transcription(provider, transcription_request)
    assert result.full_text == ""
    assert result.segments == ()
    assert TranscriptionQualityFlag.NO_SPEECH_DETECTED in result.quality_flags


@pytest.mark.parametrize(
    ("mode", "expected_exception"),
    [
        (FakeFailureMode.PROVIDER_UNAVAILABLE, TranscriptionProviderUnavailableError),
        (FakeFailureMode.TIMEOUT, TranscriptionTimeoutError),
        (FakeFailureMode.REQUEST_FAILED, TranscriptionRequestFailedError),
        (FakeFailureMode.UNSUPPORTED_LANGUAGE, UnsupportedTranscriptionLanguageError),
        (FakeFailureMode.INVALID_RESPONSE, InvalidTranscriptionResponseError),
    ],
)
def test_fake_provider_failure_modes(
    transcription_request, mode: FakeFailureMode, expected_exception: type[Exception]
) -> None:
    provider = DeterministicFakeTranscriptionProvider(
        failure_modes_by_call_id={transcription_request.call_id: mode}
    )
    with pytest.raises(expected_exception):
        run_transcription(provider, transcription_request)


def test_fake_provider_unsupported_language_without_failure_mode(transcription_request) -> None:
    provider = DeterministicFakeTranscriptionProvider(supported_languages=frozenset({"fa"}))
    with pytest.raises(UnsupportedTranscriptionLanguageError):
        run_transcription(provider, transcription_request)
