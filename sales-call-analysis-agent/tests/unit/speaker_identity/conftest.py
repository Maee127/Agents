"""Shared fixtures for speaker-identity unit tests."""

from __future__ import annotations

import pytest

from sales_call_agent.alignment.models import (
    AlignmentMethod,
    AlignmentQualityFlag,
    AlignmentResult,
    AlignmentStatus,
    SpeakerAttributedSegment,
    SpeakerCandidate,
)


@pytest.fixture
def alignment_result() -> AlignmentResult:
    return AlignmentResult(
        call_id="call-1",
        segments=(
            SpeakerAttributedSegment(
                source_segment_index=0,
                text=" SECRET_TRANSCRIPT_TOKEN_A ",
                start_seconds=0.0,
                end_seconds=1.0,
                speaker_label="SPEAKER_00",
                status=AlignmentStatus.ASSIGNED,
                alignment_method=AlignmentMethod.SEGMENT_LEVEL,
                candidates=(
                    SpeakerCandidate(
                        speaker_label="SPEAKER_00",
                        overlap_seconds=1.0,
                        overlap_ratio=1.0,
                    ),
                ),
            ),
            SpeakerAttributedSegment(
                source_segment_index=1,
                text=" SECRET_TRANSCRIPT_TOKEN_B ",
                start_seconds=1.0,
                end_seconds=2.0,
                speaker_label="SPEAKER_01",
                status=AlignmentStatus.ASSIGNED,
                alignment_method=AlignmentMethod.SEGMENT_LEVEL,
                candidates=(
                    SpeakerCandidate(
                        speaker_label="SPEAKER_01",
                        overlap_seconds=1.0,
                        overlap_ratio=1.0,
                    ),
                ),
            ),
        ),
        quality_flags=(AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,),
    )


@pytest.fixture
def empty_alignment_result() -> AlignmentResult:
    return AlignmentResult(
        call_id="call-1",
        segments=(),
        quality_flags=(AlignmentQualityFlag.NO_TRANSCRIPT_SPEECH,),
    )
