"""Deterministic fake diarization provider for tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from sales_call_agent.diarization.exceptions import (
    DiarizationProviderUnavailableError,
    DiarizationRequestFailedError,
    DiarizationTimeoutError,
    InvalidDiarizationResponseError,
    UnsupportedSpeakerConstraintError,
)
from sales_call_agent.diarization.models import (
    DiarizationConfidenceMetric,
    DiarizationConfidenceScale,
    DiarizationQualityFlag,
    DiarizationRequest,
    DiarizationResult,
    SpeakerTurn,
    has_cross_speaker_overlap,
)
from sales_call_agent.diarization.provider import DiarizationProvider


class FakeDiarizationFailureMode(StrEnum):
    """Deterministic failure modes keyed by call_id."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    REQUEST_FAILED = "request_failed"
    UNSUPPORTED_CONSTRAINT = "unsupported_constraint"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True, slots=True, kw_only=True)
class DeterministicFakeDiarizationProvider(DiarizationProvider):
    """Provider-independent fake implementation with deterministic outputs."""

    provider_name: str = "fake_diarization"
    model_name: str = "fake_diarization_v1"
    failure_modes_by_call_id: Mapping[str, FakeDiarizationFailureMode] = field(default_factory=dict)
    no_speech_call_ids: frozenset[str] = frozenset()
    single_speaker_call_ids: frozenset[str] = frozenset()
    overlapping_call_ids: frozenset[str] = frozenset()
    very_short_turns_call_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "failure_modes_by_call_id",
            MappingProxyType(dict(self.failure_modes_by_call_id)),
        )

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        mode = self.failure_modes_by_call_id.get(request.call_id)
        if mode is FakeDiarizationFailureMode.PROVIDER_UNAVAILABLE:
            raise DiarizationProviderUnavailableError("diarization provider is unavailable")
        if mode is FakeDiarizationFailureMode.TIMEOUT:
            raise DiarizationTimeoutError("diarization provider timed out")
        if mode is FakeDiarizationFailureMode.REQUEST_FAILED:
            raise DiarizationRequestFailedError("diarization request failed")
        if mode is FakeDiarizationFailureMode.UNSUPPORTED_CONSTRAINT:
            raise UnsupportedSpeakerConstraintError("speaker-count constraints are unsupported")
        if mode is FakeDiarizationFailureMode.INVALID_RESPONSE:
            return _map_fake_payload_to_result(
                payload={"turns": "not-a-list"},
                request=request,
                provider_name=self.provider_name,
                model_name=self.model_name,
            )

        if request.call_id in self.no_speech_call_ids:
            return _build_result(
                request=request,
                turns=(),
                provider_name=self.provider_name,
                model_name=self.model_name,
                extra_flags=(),
            )

        if request.call_id in self.overlapping_call_ids:
            overlapping_turns: tuple[SpeakerTurn, ...] = (
                SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=2.0),
                SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.5, end_seconds=3.0),
            )
            return _build_result(
                request=request,
                turns=overlapping_turns,
                provider_name=self.provider_name,
                model_name=self.model_name,
                extra_flags=(),
            )

        if request.call_id in self.single_speaker_call_ids:
            single_turns: tuple[SpeakerTurn, ...] = (
                SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
                SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=1.0, end_seconds=2.0),
            )
            return _build_result(
                request=request,
                turns=single_turns,
                provider_name=self.provider_name,
                model_name=self.model_name,
                extra_flags=(),
            )

        if request.call_id in self.very_short_turns_call_ids:
            short_turns: tuple[SpeakerTurn, ...] = (
                SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=0.05),
                SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=0.5, end_seconds=1.0),
            )
            return _build_result(
                request=request,
                turns=short_turns,
                provider_name=self.provider_name,
                model_name=self.model_name,
                extra_flags=(DiarizationQualityFlag.VERY_SHORT_TURNS_PRESENT,),
            )

        default_turns: tuple[SpeakerTurn, ...] = (
            SpeakerTurn(
                speaker_label="SPEAKER_00",
                start_seconds=0.0,
                end_seconds=1.0,
                provider_confidence=(
                    DiarizationConfidenceMetric(
                        name="TURN_CONFIDENCE",
                        value=0.91,
                        scale=DiarizationConfidenceScale.ZERO_TO_ONE,
                        higher_is_better=True,
                    ),
                ),
            ),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=2.0, end_seconds=3.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=3.0, end_seconds=4.0),
        )
        return _build_result(
            request=request,
            turns=default_turns,
            provider_name=self.provider_name,
            model_name=self.model_name,
            extra_flags=(),
        )


def _build_result(
    *,
    request: DiarizationRequest,
    turns: tuple[SpeakerTurn, ...],
    provider_name: str,
    model_name: str,
    extra_flags: tuple[DiarizationQualityFlag, ...],
) -> DiarizationResult:
    quality_flags = _derive_quality_flags(turns, extra_flags=extra_flags)
    return DiarizationResult(
        call_id=request.call_id,
        turns=turns,
        provider_name=provider_name,
        model_name=model_name,
        processing_duration_seconds=0.02,
        quality_flags=quality_flags,
    )


def _derive_quality_flags(
    turns: tuple[SpeakerTurn, ...],
    *,
    extra_flags: tuple[DiarizationQualityFlag, ...],
) -> tuple[DiarizationQualityFlag, ...]:
    flags: list[DiarizationQualityFlag] = list(extra_flags)
    if not turns:
        flags.append(DiarizationQualityFlag.NO_SPEECH_SEGMENTS)
        return tuple(flags)

    unique_speakers = {turn.speaker_label for turn in turns}
    if len(unique_speakers) == 1:
        flags.append(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED)
    if has_cross_speaker_overlap(turns):
        flags.append(DiarizationQualityFlag.OVERLAPPING_SPEECH_DETECTED)
    return tuple(flags)


def _map_fake_payload_to_result(
    *,
    payload: object,
    request: DiarizationRequest,
    provider_name: str,
    model_name: str,
) -> DiarizationResult:
    """Map a payload from a hypothetical external provider into domain models."""
    if not isinstance(payload, dict):
        raise InvalidDiarizationResponseError("provider response payload is invalid")

    turns_payload = payload.get("turns")
    if not isinstance(turns_payload, list):
        raise InvalidDiarizationResponseError("provider response payload is invalid")

    turns: list[SpeakerTurn] = []
    for item in turns_payload:
        if not isinstance(item, dict):
            raise InvalidDiarizationResponseError("provider response payload is invalid")
        try:
            turn = SpeakerTurn(
                speaker_label=item["speaker_label"],
                start_seconds=item["start_seconds"],
                end_seconds=item["end_seconds"],
            )
        except (KeyError, TypeError, InvalidDiarizationResponseError) as error:
            raise InvalidDiarizationResponseError("provider response payload is invalid") from error
        turns.append(turn)

    return _build_result(
        request=request,
        turns=tuple(turns),
        provider_name=provider_name,
        model_name=model_name,
        extra_flags=(),
    )
