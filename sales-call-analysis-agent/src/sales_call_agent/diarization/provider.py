"""Provider protocol and orchestration helper for diarization."""

from __future__ import annotations

from typing import Protocol

from sales_call_agent.diarization.exceptions import (
    InvalidDiarizationInputError,
    InvalidDiarizationResponseError,
)
from sales_call_agent.diarization.models import DiarizationRequest, DiarizationResult


class DiarizationProvider(Protocol):
    """Provider-independent contract for diarization adapters."""

    @property
    def provider_name(self) -> str:
        """Stable provider identifier (e.g. vendor name)."""

    @property
    def model_name(self) -> str:
        """Stable model identifier/version within the provider."""

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        """Diarize a normalized audio artifact into speaker turns."""


def run_diarization(
    provider: DiarizationProvider, request: DiarizationRequest
) -> DiarizationResult:
    """Run diarization with boundary contract checks.

    This function intentionally does not broadly catch exceptions:
    - known ``DiarizationError`` subclasses propagate unchanged;
    - programming errors also surface unchanged;
    - only explicit request/result contract mismatches are raised as
      ``InvalidDiarizationInputError`` or ``InvalidDiarizationResponseError``.

    Speaker-count behavior in v1:
    - ``exact_expected_speakers`` is a hard post-condition on the result;
    - ``min_expected_speakers`` / ``max_expected_speakers`` are provider hints
      only and do not mutate the returned result.
    """
    if not isinstance(request, DiarizationRequest):
        raise InvalidDiarizationInputError("request must be a DiarizationRequest")

    result = provider.diarize(request)
    if not isinstance(result, DiarizationResult):
        raise InvalidDiarizationResponseError("provider returned an invalid response object")
    if result.provider_name != provider.provider_name:
        raise InvalidDiarizationResponseError(
            "result provider_name does not match the provider contract"
        )
    if result.model_name != provider.model_name:
        raise InvalidDiarizationResponseError(
            "result model_name does not match the provider contract"
        )
    if result.call_id != request.call_id:
        raise InvalidDiarizationResponseError("result call_id does not match the request")

    if (
        request.exact_expected_speakers is not None
        and result.speaker_count != request.exact_expected_speakers
    ):
        raise InvalidDiarizationResponseError(
            "detected speaker count does not match exact expected speaker count"
        )

    return result
