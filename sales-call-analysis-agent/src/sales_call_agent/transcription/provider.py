"""Provider protocol and orchestration helper for transcription."""

from __future__ import annotations

from typing import Protocol

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionInputError,
    InvalidTranscriptionResponseError,
)
from sales_call_agent.transcription.models import TranscriptionRequest, TranscriptionResult


class TranscriptionProvider(Protocol):
    """Provider-independent contract for transcription adapters."""

    @property
    def provider_name(self) -> str:
        """Stable provider identifier (e.g. vendor name)."""

    @property
    def model_name(self) -> str:
        """Stable model identifier/version within the provider."""

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Transcribe a normalized audio artifact."""


def run_transcription(
    provider: TranscriptionProvider, request: TranscriptionRequest
) -> TranscriptionResult:
    """Run transcription with boundary contract checks.

    This function intentionally does not broadly catch exceptions:
    - known ``TranscriptionError`` subclasses propagate unchanged;
    - programming errors also surface unchanged;
    - only explicit request/result contract mismatches are raised as
      ``InvalidTranscriptionInputError`` or ``InvalidTranscriptionResponseError``.
    """
    if not isinstance(request, TranscriptionRequest):
        raise InvalidTranscriptionInputError("request must be a TranscriptionRequest")

    result = provider.transcribe(request)
    if not isinstance(result, TranscriptionResult):
        raise InvalidTranscriptionResponseError("provider returned an invalid response object")
    if result.provider_name != provider.provider_name:
        raise InvalidTranscriptionResponseError(
            "result provider_name does not match the provider contract"
        )
    if result.model_name != provider.model_name:
        raise InvalidTranscriptionResponseError(
            "result model_name does not match the provider contract"
        )
    if result.call_id != request.call_id:
        raise InvalidTranscriptionResponseError("result call_id does not match the request")
    return result
