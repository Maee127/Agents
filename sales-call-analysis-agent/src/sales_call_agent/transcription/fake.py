"""Deterministic fake transcription provider for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionResponseError,
    TranscriptionProviderUnavailableError,
    TranscriptionRequestFailedError,
    TranscriptionTimeoutError,
    UnsupportedTranscriptionLanguageError,
)
from sales_call_agent.transcription.models import (
    ConfidenceScale,
    ProviderConfidenceMetric,
    TranscriptionQualityFlag,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegment,
    TranscriptWord,
)
from sales_call_agent.transcription.provider import TranscriptionProvider


class FakeFailureMode(StrEnum):
    """Deterministic failure modes keyed by call_id."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    REQUEST_FAILED = "request_failed"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True, slots=True, kw_only=True)
class DeterministicFakeTranscriptionProvider(TranscriptionProvider):
    """Provider-independent fake implementation with deterministic outputs."""

    provider_name: str = "fake_asr"
    model_name: str = "fake_model_v1"
    default_language: str = "en"
    supported_languages: frozenset[str] = frozenset({"en"})
    no_speech_call_ids: frozenset[str] = frozenset()
    failure_modes_by_call_id: dict[str, FakeFailureMode] = field(default_factory=dict)

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        mode = self.failure_modes_by_call_id.get(request.call_id)
        if mode is FakeFailureMode.PROVIDER_UNAVAILABLE:
            raise TranscriptionProviderUnavailableError("transcription provider is unavailable")
        if mode is FakeFailureMode.TIMEOUT:
            raise TranscriptionTimeoutError("transcription provider timed out")
        if mode is FakeFailureMode.REQUEST_FAILED:
            raise TranscriptionRequestFailedError("transcription request failed")
        if mode is FakeFailureMode.UNSUPPORTED_LANGUAGE:
            raise UnsupportedTranscriptionLanguageError("requested language is unsupported")
        if mode is FakeFailureMode.INVALID_RESPONSE:
            return _map_fake_payload_to_result(
                payload={"segments": "not-a-list"},
                request=request,
                provider_name=self.provider_name,
                model_name=self.model_name,
            )

        language = request.expected_language or self.default_language
        if language not in self.supported_languages:
            raise UnsupportedTranscriptionLanguageError("requested language is unsupported")

        if request.call_id in self.no_speech_call_ids:
            return TranscriptionResult(
                call_id=request.call_id,
                full_text="",
                segments=(),
                detected_language=language,
                language_confidence=0.99,
                provider_name=self.provider_name,
                model_name=self.model_name,
                processing_duration_seconds=0.01,
                quality_flags=(TranscriptionQualityFlag.NO_SPEECH_DETECTED,),
            )

        segments = (
            TranscriptSegment(
                text="hello",
                start_seconds=0.0,
                end_seconds=0.5,
                words=(TranscriptWord(text="hello", start_seconds=0.0, end_seconds=0.5),),
            ),
            TranscriptSegment(
                text="world",
                start_seconds=0.5,
                end_seconds=1.0,
                words=(TranscriptWord(text="world", start_seconds=0.5, end_seconds=1.0),),
            ),
        )
        return TranscriptionResult(
            call_id=request.call_id,
            full_text="hello world",
            segments=segments,
            detected_language=language,
            language_confidence=0.99,
            provider_name=self.provider_name,
            model_name=self.model_name,
            processing_duration_seconds=0.02,
            provider_confidence=(
                ProviderConfidenceMetric(
                    name="AVG_LOGPROB",
                    value=-0.2,
                    scale=ConfidenceScale.LOG_PROBABILITY,
                ),
            ),
            warning_codes=(),
        )


def _map_fake_payload_to_result(
    *,
    payload: object,
    request: TranscriptionRequest,
    provider_name: str,
    model_name: str,
) -> TranscriptionResult:
    """Map a payload from a hypothetical external provider into domain models."""
    if not isinstance(payload, dict):
        raise InvalidTranscriptionResponseError("provider response payload is invalid")

    segments_payload = payload.get("segments")
    if not isinstance(segments_payload, list):
        raise InvalidTranscriptionResponseError("provider response payload is invalid")

    segments: list[TranscriptSegment] = []
    for item in segments_payload:
        if not isinstance(item, dict):
            raise InvalidTranscriptionResponseError("provider response payload is invalid")
        try:
            segment = TranscriptSegment(
                text=item["text"],
                start_seconds=item["start_seconds"],
                end_seconds=item["end_seconds"],
            )
        except (KeyError, TypeError, InvalidTranscriptionResponseError) as error:
            raise InvalidTranscriptionResponseError(
                "provider response payload is invalid"
            ) from error
        segments.append(segment)

    full_text = payload.get("full_text", "")
    return TranscriptionResult(
        call_id=request.call_id,
        full_text=full_text,
        segments=tuple(segments),
        detected_language=payload.get("detected_language"),
        language_confidence=payload.get("language_confidence"),
        provider_name=provider_name,
        model_name=model_name,
        processing_duration_seconds=payload.get("processing_duration_seconds"),
    )
