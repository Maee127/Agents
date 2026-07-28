"""Evaluation provider protocol and request/response boundary validation."""

from __future__ import annotations

from typing import Protocol

from sales_call_agent.alignment.models import (
    AlignmentStatus,
    SpeakerAttributedSegment,
    SpeakerAttributedWord,
)
from sales_call_agent.evaluation.exceptions import (
    InvalidEvaluationInputError,
    InvalidEvaluationResponseError,
)
from sales_call_agent.evaluation.models import (
    CallEvaluationResult,
    CriterionEvaluation,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationRequest,
    TranscriptEvidenceSpan,
)
from sales_call_agent.knowledge.models import EvidenceRequirement, RubricCriterion
from sales_call_agent.speaker_identity.models import SpeakerRole


class EvaluationProvider(Protocol):
    """Provider interface for call evaluation implementations."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def evaluate(self, request: EvaluationRequest) -> CallEvaluationResult: ...


def run_evaluation(
    provider: EvaluationProvider,
    request: EvaluationRequest,
) -> CallEvaluationResult:
    """Run one provider evaluation and validate cross-model invariants."""
    if not isinstance(request, EvaluationRequest):
        raise InvalidEvaluationInputError("request must be an EvaluationRequest")

    result = provider.evaluate(request)
    if not isinstance(result, CallEvaluationResult):
        raise InvalidEvaluationResponseError("provider must return CallEvaluationResult")

    if result.call_id != request.call_id:
        raise InvalidEvaluationResponseError("result call_id must match request call_id")
    if result.rubric_id != request.rubric.rubric_id:
        raise InvalidEvaluationResponseError("result rubric_id must match request rubric_id")
    if result.rubric_version != request.rubric.version:
        raise InvalidEvaluationResponseError(
            "result rubric_version must match request rubric version"
        )
    if result.provider_name != provider.provider_name:
        raise InvalidEvaluationResponseError("result provider_name must match provider identity")
    if result.model_name != provider.model_name:
        raise InvalidEvaluationResponseError("result model_name must match provider model identity")

    expected_ids = tuple(criterion.criterion_id for criterion in request.rubric.criteria)
    actual_ids = tuple(item.criterion_id for item in result.criterion_evaluations)
    if actual_ids != expected_ids:
        raise InvalidEvaluationResponseError(
            "criterion evaluations must match rubric criteria exactly and in order"
        )

    role_by_label = {
        assignment.speaker_label: assignment.role
        for assignment in request.role_assignment.assignments
    }
    segment_by_index = {
        segment.source_segment_index: segment for segment in request.alignment.segments
    }

    for criterion, evaluation in zip(
        request.rubric.criteria,
        result.criterion_evaluations,
        strict=True,
    ):
        _validate_criterion_evaluation(
            criterion=criterion,
            evaluation=evaluation,
            role_by_label=role_by_label,
            segment_by_index=segment_by_index,
        )

    return result


def _validate_criterion_evaluation(
    *,
    criterion: RubricCriterion,
    evaluation: CriterionEvaluation,
    role_by_label: dict[str, SpeakerRole],
    segment_by_index: dict[int, SpeakerAttributedSegment],
) -> None:
    requirement = criterion.evidence_requirement

    if evaluation.status is CriterionEvaluationStatus.SCORED:
        assert evaluation.score is not None
        assert evaluation.score_level_label is not None
        _validate_score_membership(criterion, evaluation.score, evaluation.score_level_label)
        if evaluation.absence_evidence is not None:
            if not requirement.absence_can_be_evidence:
                raise InvalidEvaluationResponseError(
                    "absence evidence is not permitted for this criterion"
                )
            if evaluation.evidence_spans:
                raise InvalidEvaluationResponseError(
                    "scored transcript evidence and absence evidence cannot coexist"
                )
            if (
                evaluation.reason_code
                is not CriterionEvaluationReason.SUPPORTED_BY_ABSENCE_EVIDENCE
            ):
                raise InvalidEvaluationResponseError(
                    "scored absence evidence requires absence support reason"
                )
            _validate_absence_evidence(evaluation, segment_by_index, role_by_label)
            _validate_role_requirements_for_absence(requirement, evaluation)
        else:
            if (
                evaluation.reason_code
                is not CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE
            ):
                raise InvalidEvaluationResponseError(
                    "scored transcript evidence requires transcript support reason"
                )
            _validate_transcript_spans(evaluation.evidence_spans, segment_by_index, role_by_label)
            if len(evaluation.evidence_spans) < requirement.minimum_evidence_spans:
                raise InvalidEvaluationResponseError(
                    "criterion transcript evidence span count is below minimum requirement"
                )
            _validate_role_requirements_for_spans(requirement, evaluation.evidence_spans)
    elif evaluation.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE:
        if evaluation.evidence_spans:
            _validate_transcript_spans(evaluation.evidence_spans, segment_by_index, role_by_label)
    elif evaluation.status is CriterionEvaluationStatus.NOT_APPLICABLE:
        pass

    if requirement.human_review_required and not evaluation.human_review_required:
        raise InvalidEvaluationResponseError(
            "criterion requiring human review must set human_review_required"
        )


def _validate_score_membership(
    criterion: RubricCriterion,
    score: float,
    score_level_label: str,
) -> None:
    matched = [
        level for level in criterion.scoring_scale.levels if float(level.score) == float(score)
    ]
    if not matched:
        raise InvalidEvaluationResponseError("criterion score must match allowed score level")
    if matched[0].label != score_level_label:
        raise InvalidEvaluationResponseError(
            "score_level_label must match rubric score level label"
        )


def _validate_transcript_spans(
    spans: tuple[TranscriptEvidenceSpan, ...],
    segment_by_index: dict[int, SpeakerAttributedSegment],
    role_by_label: dict[str, SpeakerRole],
) -> None:
    if not spans:
        raise InvalidEvaluationResponseError("transcript evidence spans are required")
    for span in spans:
        segment = segment_by_index.get(span.source_segment_index)
        if segment is None:
            raise InvalidEvaluationResponseError("evidence span segment index must exist")

        resolved_role = role_by_label.get(span.speaker_label)
        if resolved_role is None:
            raise InvalidEvaluationResponseError("evidence span speaker label must exist")
        if resolved_role is not span.speaker_role:
            raise InvalidEvaluationResponseError("evidence span role must match role assignment")

        if span.source_word_start_index is None and span.source_word_end_index is None:
            if segment.speaker_label != span.speaker_label:
                raise InvalidEvaluationResponseError(
                    "segment-level evidence speaker label must match aligned segment"
                )
            continue

        assert span.source_word_start_index is not None
        assert span.source_word_end_index is not None
        words_by_source_index = {word.source_word_index: word for word in segment.words}
        for source_word_index in range(
            span.source_word_start_index, span.source_word_end_index + 1
        ):
            word = words_by_source_index.get(source_word_index)
            if word is None:
                raise InvalidEvaluationResponseError(
                    "word-level evidence indexes must reference existing source_word_index values"
                )
            _validate_word_alignment(word, span.speaker_label)


def _validate_word_alignment(word: SpeakerAttributedWord, expected_speaker_label: str) -> None:
    if word.status is not AlignmentStatus.ASSIGNED:
        raise InvalidEvaluationResponseError("word-level evidence requires assigned aligned words")
    if word.speaker_label != expected_speaker_label:
        raise InvalidEvaluationResponseError("one evidence span must not cross speakers")


def _validate_role_requirements_for_spans(
    requirement: EvidenceRequirement,
    spans: tuple[TranscriptEvidenceSpan, ...],
) -> None:
    if requirement.seller_role_required and not any(
        span.speaker_role is SpeakerRole.SELLER for span in spans
    ):
        raise InvalidEvaluationResponseError(
            "seller_role_required criteria need seller evidence spans"
        )
    if requirement.customer_context_required and not any(
        span.speaker_role is SpeakerRole.CUSTOMER for span in spans
    ):
        raise InvalidEvaluationResponseError(
            "customer_context_required criteria need customer evidence spans"
        )


def _validate_absence_evidence(
    evaluation: CriterionEvaluation,
    segment_by_index: dict[int, SpeakerAttributedSegment],
    role_by_label: dict[str, SpeakerRole],
) -> None:
    assert evaluation.absence_evidence is not None
    absence = evaluation.absence_evidence
    for segment_index in absence.reviewed_segment_indexes:
        segment = segment_by_index.get(segment_index)
        if segment is None:
            raise InvalidEvaluationResponseError("absence reviewed segment indexes must exist")
        if (
            segment.end_seconds <= absence.scope_start_seconds
            or segment.start_seconds >= absence.scope_end_seconds
        ):
            raise InvalidEvaluationResponseError(
                "absence reviewed segments must intersect absence scope"
            )
    if absence.speaker_role is not None:
        matching_segments = [
            segment_by_index[index]
            for index in absence.reviewed_segment_indexes
            if segment_by_index[index].speaker_label is not None
        ]
        for segment in matching_segments:
            assert segment.speaker_label is not None
            resolved = role_by_label.get(segment.speaker_label)
            if resolved is None:
                raise InvalidEvaluationResponseError(
                    "absence evidence speaker labels must exist in role assignments"
                )
            if resolved is not absence.speaker_role:
                raise InvalidEvaluationResponseError(
                    "absence evidence speaker_role must match role assignment"
                )


def _validate_role_requirements_for_absence(
    requirement: EvidenceRequirement,
    evaluation: CriterionEvaluation,
) -> None:
    assert evaluation.absence_evidence is not None
    role = evaluation.absence_evidence.speaker_role
    if requirement.seller_role_required and role is not SpeakerRole.SELLER:
        raise InvalidEvaluationResponseError(
            "seller_role_required criteria need seller-oriented absence evidence"
        )
    if requirement.customer_context_required and role is not SpeakerRole.CUSTOMER:
        raise InvalidEvaluationResponseError(
            "customer_context_required criteria need customer-oriented absence evidence"
        )
