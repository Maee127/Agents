"""Deterministic transcript-speaker alignment engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sales_call_agent.alignment.exceptions import InvalidAlignmentInputError
from sales_call_agent.alignment.models import (
    AlignmentConfig,
    AlignmentMethod,
    AlignmentQualityFlag,
    AlignmentRequest,
    AlignmentResult,
    AlignmentStatus,
    SpeakerAttributedSegment,
    SpeakerAttributedWord,
    SpeakerCandidate,
)
from sales_call_agent.diarization.models import (
    DiarizationQualityFlag,
    DiarizationResult,
    SpeakerTurn,
)
from sales_call_agent.transcription.models import (
    TranscriptionQualityFlag,
    TranscriptionResult,
    TranscriptSegment,
)


def align_transcript_with_speakers(request: AlignmentRequest) -> AlignmentResult:
    """Align transcript units to anonymous diarization speaker labels."""
    _validate_source_contracts(request.transcription, request.diarization)

    transcription = request.transcription
    diarization = request.diarization
    config = request.config

    if not transcription.segments:
        flags: list[AlignmentQualityFlag] = [AlignmentQualityFlag.NO_TRANSCRIPT_SPEECH]
        if not diarization.turns:
            flags.append(AlignmentQualityFlag.NO_DIARIZATION_TURNS)
        return AlignmentResult(
            call_id=request.call_id,
            segments=(),
            quality_flags=tuple(flags),
        )

    attributed_segments: list[SpeakerAttributedSegment] = []
    for segment_index, source_segment in enumerate(transcription.segments):
        attributed_segments.append(
            _align_segment(
                source_segment=source_segment,
                source_segment_index=segment_index,
                diarization=diarization,
                config=config,
            )
        )

    quality_flags = _derive_quality_flags(
        segments=tuple(attributed_segments),
        diarization=diarization,
    )
    return AlignmentResult(
        call_id=request.call_id,
        segments=tuple(attributed_segments),
        quality_flags=quality_flags,
    )


def _validate_source_contracts(
    transcription: TranscriptionResult,
    diarization: DiarizationResult,
) -> None:
    transcription_no_speech = (
        TranscriptionQualityFlag.NO_SPEECH_DETECTED in transcription.quality_flags
    )
    diarization_no_speech = DiarizationQualityFlag.NO_SPEECH_SEGMENTS in diarization.quality_flags

    if transcription_no_speech and transcription.segments:
        raise InvalidAlignmentInputError("transcription contract is contradictory")
    if (not transcription_no_speech) and not transcription.segments:
        raise InvalidAlignmentInputError("transcription contract is contradictory")
    if diarization_no_speech and diarization.turns:
        raise InvalidAlignmentInputError("diarization contract is contradictory")
    if (not diarization_no_speech) and not diarization.turns:
        raise InvalidAlignmentInputError("diarization contract is contradictory")


def _align_segment(
    *,
    source_segment: TranscriptSegment,
    source_segment_index: int,
    diarization: DiarizationResult,
    config: AlignmentConfig,
) -> SpeakerAttributedSegment:
    words = source_segment.words
    has_words = len(words) > 0
    has_timed_words = has_words and all(
        word.start_seconds is not None and word.end_seconds is not None for word in words
    )

    if has_timed_words and config.word_level_enabled:
        return _align_segment_with_words(
            source_segment=source_segment,
            source_segment_index=source_segment_index,
            diarization=diarization,
            config=config,
        )

    return _align_segment_interval(
        source_segment=source_segment,
        source_segment_index=source_segment_index,
        diarization=diarization,
        config=config,
        inherit_words=has_words,
    )


def _align_segment_with_words(
    *,
    source_segment: TranscriptSegment,
    source_segment_index: int,
    diarization: DiarizationResult,
    config: AlignmentConfig,
) -> SpeakerAttributedSegment:
    attributed_words: list[SpeakerAttributedWord] = []
    for word_index, source_word in enumerate(source_segment.words):
        assert source_word.start_seconds is not None and source_word.end_seconds is not None
        decision = _align_interval(
            start_seconds=source_word.start_seconds,
            end_seconds=source_word.end_seconds,
            diarization_turns=diarization.turns,
            config=config,
        )
        attributed_words.append(
            SpeakerAttributedWord(
                source_word_index=word_index,
                text=source_word.text,
                start_seconds=source_word.start_seconds,
                end_seconds=source_word.end_seconds,
                speaker_label=decision.speaker_label,
                status=decision.status,
                candidates=decision.candidates,
                overlapping_speech=decision.overlapping_speech,
            )
        )

    segment_status, segment_speaker_label = _summarize_word_level_segment(attributed_words)
    segment_candidates = _segment_candidates_from_words(
        words=attributed_words,
        segment_start=source_segment.start_seconds,
        segment_end=source_segment.end_seconds,
        summary_status=segment_status,
        summary_speaker_label=segment_speaker_label,
    )
    return SpeakerAttributedSegment(
        source_segment_index=source_segment_index,
        text=source_segment.text,
        start_seconds=source_segment.start_seconds,
        end_seconds=source_segment.end_seconds,
        speaker_label=segment_speaker_label,
        status=segment_status,
        alignment_method=AlignmentMethod.WORD_LEVEL,
        words=tuple(attributed_words),
        candidates=segment_candidates,
        overlapping_speech=any(word.overlapping_speech for word in attributed_words),
    )


def _align_segment_interval(
    *,
    source_segment: TranscriptSegment,
    source_segment_index: int,
    diarization: DiarizationResult,
    config: AlignmentConfig,
    inherit_words: bool,
) -> SpeakerAttributedSegment:
    decision = _align_interval(
        start_seconds=source_segment.start_seconds,
        end_seconds=source_segment.end_seconds,
        diarization_turns=diarization.turns,
        config=config,
    )
    attributed_words: tuple[SpeakerAttributedWord, ...] = ()
    if inherit_words:
        inherited: list[SpeakerAttributedWord] = []
        for word_index, source_word in enumerate(source_segment.words):
            inherited.append(
                SpeakerAttributedWord(
                    source_word_index=word_index,
                    text=source_word.text,
                    start_seconds=source_word.start_seconds,
                    end_seconds=source_word.end_seconds,
                    speaker_label=decision.speaker_label,
                    status=decision.status,
                    candidates=decision.candidates,
                    overlapping_speech=decision.overlapping_speech,
                )
            )
        attributed_words = tuple(inherited)

    return SpeakerAttributedSegment(
        source_segment_index=source_segment_index,
        text=source_segment.text,
        start_seconds=source_segment.start_seconds,
        end_seconds=source_segment.end_seconds,
        speaker_label=decision.speaker_label,
        status=decision.status,
        alignment_method=AlignmentMethod.SEGMENT_LEVEL,
        words=attributed_words,
        candidates=decision.candidates,
        overlapping_speech=decision.overlapping_speech,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _IntervalDecision:
    status: AlignmentStatus
    speaker_label: str | None
    candidates: tuple[SpeakerCandidate, ...]
    overlapping_speech: bool


def _align_interval(
    *,
    start_seconds: float,
    end_seconds: float,
    diarization_turns: Sequence[SpeakerTurn],
    config: AlignmentConfig,
) -> _IntervalDecision:
    candidates = _build_candidates(
        transcript_start=start_seconds,
        transcript_end=end_seconds,
        diarization_turns=diarization_turns,
        tolerance_seconds=config.boundary_tolerance_seconds,
    )
    overlap_intersects_content = _cross_overlap_intersects_interval(
        interval_start=start_seconds,
        interval_end=end_seconds,
        turns=diarization_turns,
    )
    if not candidates:
        return _IntervalDecision(
            status=AlignmentStatus.UNASSIGNED,
            speaker_label=None,
            candidates=(),
            overlapping_speech=overlap_intersects_content,
        )

    top = candidates[0]
    if top.overlap_ratio < config.minimum_overlap_ratio:
        return _IntervalDecision(
            status=AlignmentStatus.UNASSIGNED,
            speaker_label=None,
            candidates=candidates,
            overlapping_speech=overlap_intersects_content,
        )

    if len(candidates) > 1:
        second = candidates[1]
        if top.overlap_ratio - second.overlap_ratio <= config.ambiguity_margin:
            return _IntervalDecision(
                status=AlignmentStatus.AMBIGUOUS,
                speaker_label=None,
                candidates=candidates,
                overlapping_speech=overlap_intersects_content,
            )

    return _IntervalDecision(
        status=AlignmentStatus.ASSIGNED,
        speaker_label=top.speaker_label,
        candidates=candidates,
        overlapping_speech=overlap_intersects_content,
    )


def _build_candidates(
    *,
    transcript_start: float,
    transcript_end: float,
    diarization_turns: Sequence[SpeakerTurn],
    tolerance_seconds: float,
) -> tuple[SpeakerCandidate, ...]:
    transcript_duration = transcript_end - transcript_start
    overlaps_by_speaker: dict[str, float] = {}
    intervals_by_speaker: dict[str, list[tuple[float, float]]] = defaultdict(list)

    for turn in diarization_turns:
        effective_start = turn.start_seconds - tolerance_seconds
        effective_end = turn.end_seconds + tolerance_seconds
        intersect_start = max(transcript_start, effective_start)
        intersect_end = min(transcript_end, effective_end)
        if intersect_end <= intersect_start:
            continue
        intervals_by_speaker[turn.speaker_label].append((intersect_start, intersect_end))

    for speaker_label, intervals in intervals_by_speaker.items():
        unioned = _union_intervals(intervals)
        overlap_seconds = sum(end - start for start, end in unioned)
        overlap_seconds = min(overlap_seconds, transcript_duration)
        if overlap_seconds <= 0:
            continue
        overlaps_by_speaker[speaker_label] = overlap_seconds

    candidates: list[SpeakerCandidate] = []
    for speaker_label, overlap_seconds in overlaps_by_speaker.items():
        ratio = overlap_seconds / transcript_duration if transcript_duration > 0 else 0.0
        ratio = min(max(ratio, 0.0), 1.0)
        candidates.append(
            SpeakerCandidate(
                speaker_label=speaker_label,
                overlap_seconds=overlap_seconds,
                overlap_ratio=ratio,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.overlap_ratio,
            -candidate.overlap_seconds,
            candidate.speaker_label,
        )
    )
    return tuple(candidates)


def _union_intervals(intervals: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    if not intervals:
        return ()
    ordered = sorted(intervals, key=lambda interval: (interval[0], interval[1]))
    result: list[tuple[float, float]] = []
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        result.append((current_start, current_end))
        current_start, current_end = start, end
    result.append((current_start, current_end))
    return tuple(result)


def _cross_overlap_intersects_interval(
    *,
    interval_start: float,
    interval_end: float,
    turns: Sequence[SpeakerTurn],
) -> bool:
    for left_index, left_turn in enumerate(turns):
        for right_turn in turns[left_index + 1 :]:
            if left_turn.speaker_label == right_turn.speaker_label:
                continue
            if not _intervals_overlap(
                left_turn.start_seconds,
                left_turn.end_seconds,
                right_turn.start_seconds,
                right_turn.end_seconds,
            ):
                continue
            if _intervals_overlap(
                interval_start,
                interval_end,
                max(left_turn.start_seconds, right_turn.start_seconds),
                min(left_turn.end_seconds, right_turn.end_seconds),
            ):
                return True
    return False


def _intervals_overlap(
    first_start: float, first_end: float, second_start: float, second_end: float
) -> bool:
    return first_start < second_end and second_start < first_end


def _summarize_word_level_segment(
    words: Sequence[SpeakerAttributedWord],
) -> tuple[AlignmentStatus, str | None]:
    if any(word.status is AlignmentStatus.AMBIGUOUS for word in words):
        return (AlignmentStatus.AMBIGUOUS, None)

    assigned_labels = {
        word.speaker_label
        for word in words
        if word.status is AlignmentStatus.ASSIGNED and word.speaker_label is not None
    }
    if len(assigned_labels) > 1:
        return (AlignmentStatus.AMBIGUOUS, None)
    if len(assigned_labels) == 1:
        only_label = next(iter(assigned_labels))
        return (AlignmentStatus.ASSIGNED, only_label)
    return (AlignmentStatus.UNASSIGNED, None)


def _segment_candidates_from_words(
    *,
    words: Sequence[SpeakerAttributedWord],
    segment_start: float,
    segment_end: float,
    summary_status: AlignmentStatus,
    summary_speaker_label: str | None,
) -> tuple[SpeakerCandidate, ...]:
    duration = segment_end - segment_start
    if duration <= 0:
        return ()

    totals: dict[str, float] = defaultdict(float)
    for word in words:
        for candidate in word.candidates:
            totals[candidate.speaker_label] += candidate.overlap_seconds

    if summary_status is AlignmentStatus.UNASSIGNED and not totals:
        return ()

    candidates: list[SpeakerCandidate] = []
    for label, total_seconds in totals.items():
        positive = min(total_seconds, duration)
        if positive <= 0:
            continue
        ratio = min(max(positive / duration, 0.0), 1.0)
        candidates.append(
            SpeakerCandidate(
                speaker_label=label,
                overlap_seconds=positive,
                overlap_ratio=ratio,
            )
        )
    candidates.sort(
        key=lambda candidate: (
            -candidate.overlap_ratio,
            -candidate.overlap_seconds,
            candidate.speaker_label,
        )
    )

    if summary_status is AlignmentStatus.ASSIGNED and summary_speaker_label is not None:
        if not candidates:
            return (
                SpeakerCandidate(
                    speaker_label=summary_speaker_label,
                    overlap_seconds=duration,
                    overlap_ratio=1.0,
                ),
            )
        top = candidates[0]
        if top.speaker_label != summary_speaker_label:
            candidates.sort(
                key=lambda candidate: (
                    candidate.speaker_label != summary_speaker_label,
                    -candidate.overlap_ratio,
                    -candidate.overlap_seconds,
                    candidate.speaker_label,
                )
            )
    return tuple(candidates)


def _derive_quality_flags(
    *,
    segments: tuple[SpeakerAttributedSegment, ...],
    diarization: DiarizationResult,
) -> tuple[AlignmentQualityFlag, ...]:
    flags: list[AlignmentQualityFlag] = []
    if not diarization.turns:
        flags.append(AlignmentQualityFlag.NO_DIARIZATION_TURNS)

    units: list[SpeakerAttributedSegment | SpeakerAttributedWord] = []
    for segment in segments:
        units.extend(segment.words or (segment,))

    has_unassigned = any(unit.status is AlignmentStatus.UNASSIGNED for unit in units)
    has_ambiguous = any(unit.status is AlignmentStatus.AMBIGUOUS for unit in units)
    has_overlap = any(unit.overlapping_speech for unit in units)
    assigned_count = len([unit for unit in units if unit.status is AlignmentStatus.ASSIGNED])
    methods = {segment.alignment_method for segment in segments}

    if has_unassigned:
        flags.append(AlignmentQualityFlag.UNASSIGNED_CONTENT_PRESENT)
    if has_ambiguous:
        flags.append(AlignmentQualityFlag.AMBIGUOUS_CONTENT_PRESENT)
    if has_overlap:
        flags.append(AlignmentQualityFlag.OVERLAPPING_SPEECH_PRESENT)
    if AlignmentMethod.SEGMENT_LEVEL in methods:
        flags.append(AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED)
    if len(methods) > 1:
        flags.append(AlignmentQualityFlag.MIXED_ALIGNMENT_METHODS)
    if assigned_count > 0 and (has_unassigned or has_ambiguous):
        flags.append(AlignmentQualityFlag.PARTIAL_ALIGNMENT)
    return tuple(flags)
