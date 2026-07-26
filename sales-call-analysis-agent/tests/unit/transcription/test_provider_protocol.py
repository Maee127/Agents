"""Unit tests for transcription provider boundary behavior."""

from __future__ import annotations

import pytest

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionResponseError,
    TranscriptionProviderUnavailableError,
)
from sales_call_agent.transcription.models import (
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegment,
)
from sales_call_agent.transcription.provider import run_transcription


class _GoodProvider:
    provider_name = "fake_asr"
    model_name = "fake_model_v1"

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        return TranscriptionResult(
            call_id=request.call_id,
            full_text="hello",
            segments=(TranscriptSegment(text="hello", start_seconds=0.0, end_seconds=1.0),),
            provider_name=self.provider_name,
            model_name=self.model_name,
        )


def _request() -> TranscriptionRequest:
    return TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path="normalized/hash.asr.wav",
        normalized_audio_hash="hash",
    )


def test_run_transcription_success() -> None:
    result = run_transcription(_GoodProvider(), _request())
    assert result.call_id == "call-1"


def test_provider_name_mismatch_is_rejected() -> None:
    class _BadProviderName(_GoodProvider):
        def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
            result = super().transcribe(request)
            return TranscriptionResult(
                call_id=result.call_id,
                full_text=result.full_text,
                segments=result.segments,
                provider_name="other_provider",
                model_name=result.model_name,
            )

    with pytest.raises(InvalidTranscriptionResponseError, match="provider_name"):
        run_transcription(_BadProviderName(), _request())


def test_model_name_mismatch_is_rejected() -> None:
    class _BadModelName(_GoodProvider):
        def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
            result = super().transcribe(request)
            return TranscriptionResult(
                call_id=result.call_id,
                full_text=result.full_text,
                segments=result.segments,
                provider_name=result.provider_name,
                model_name="other_model",
            )

    with pytest.raises(InvalidTranscriptionResponseError, match="model_name"):
        run_transcription(_BadModelName(), _request())


def test_call_id_mismatch_is_rejected() -> None:
    class _BadCallId(_GoodProvider):
        def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
            result = super().transcribe(request)
            return TranscriptionResult(
                call_id="different-call-id",
                full_text=result.full_text,
                segments=result.segments,
                provider_name=result.provider_name,
                model_name=result.model_name,
            )

    with pytest.raises(InvalidTranscriptionResponseError, match="call_id"):
        run_transcription(_BadCallId(), _request())


def test_known_transcription_exception_propagates_unchanged() -> None:
    class _UnavailableProvider(_GoodProvider):
        def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
            raise TranscriptionProviderUnavailableError("transcription provider is unavailable")

    with pytest.raises(TranscriptionProviderUnavailableError, match="unavailable"):
        run_transcription(_UnavailableProvider(), _request())


def test_programming_exception_is_not_broadly_wrapped() -> None:
    class _BuggyProvider(_GoodProvider):
        def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
            raise RuntimeError("unexpected bug")

    with pytest.raises(RuntimeError, match="unexpected bug"):
        run_transcription(_BuggyProvider(), _request())


def test_invalid_return_type_is_rejected() -> None:
    class _WrongTypeProvider(_GoodProvider):
        def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:  # type: ignore[override]
            return "not-a-result"  # type: ignore[return-value]

    with pytest.raises(InvalidTranscriptionResponseError, match="invalid response object"):
        run_transcription(_WrongTypeProvider(), _request())
