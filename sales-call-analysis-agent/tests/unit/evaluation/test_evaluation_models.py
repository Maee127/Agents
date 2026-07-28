"""Unit tests for evaluation models and local invariants."""

from __future__ import annotations

from dataclasses import fields

import pytest

from sales_call_agent.alignment.models import AlignmentResult
from sales_call_agent.evaluation.exceptions import (
    InvalidEvaluationInputError,
    InvalidEvaluationResponseError,
)
from sales_call_agent.evaluation.models import (
    AbsenceEvidence,
    AbsenceEvidenceReason,
    CallEvaluationResult,
    CriterionEvaluation,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationQualityFlag,
    HumanReviewReason,
    TranscriptEvidenceSpan,
)
from sales_call_agent.knowledge.models import RubricStatus, SalesRubric
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentQualityFlag,
    RoleAssignmentResult,
    SpeakerRole,
)


def test_result_has_no_all_criteria_represented_property() -> None:
    assert "all_criteria_represented" not in {current for current in dir(CallEvaluationResult)}


def test_request_requires_complete_role_coverage(
    alignment_result: AlignmentResult,
    role_assignment_result: RoleAssignmentResult,
    approved_rubric: SalesRubric,
) -> None:
    from sales_call_agent.speaker_identity.models import RoleAssignmentResult

    incomplete = RoleAssignmentResult(
        call_id=role_assignment_result.call_id,
        assignments=(role_assignment_result.assignments[0],),
        quality_flags=(RoleAssignmentQualityFlag.SINGLE_SPEAKER_CALL,),
    )
    with pytest.raises(InvalidEvaluationInputError, match="exactly match"):
        from sales_call_agent.evaluation.models import EvaluationRequest

        EvaluationRequest(
            call_id=alignment_result.call_id,
            alignment=alignment_result,
            role_assignment=incomplete,
            rubric=approved_rubric,
        )


def test_request_requires_approved_rubric(
    alignment_result: AlignmentResult,
    role_assignment_result: RoleAssignmentResult,
    approved_rubric: SalesRubric,
) -> None:
    from sales_call_agent.evaluation.models import EvaluationRequest
    from sales_call_agent.knowledge.models import SalesRubric

    draft = SalesRubric(
        rubric_id=approved_rubric.rubric_id,
        name="name",
        version=approved_rubric.version,
        description="desc",
        language="en",
        status=RubricStatus.DRAFT,
        criteria=approved_rubric.criteria,
    )
    with pytest.raises(InvalidEvaluationInputError, match="APPROVED"):
        EvaluationRequest(
            call_id=alignment_result.call_id,
            alignment=alignment_result,
            role_assignment=role_assignment_result,
            rubric=draft,
        )


def test_not_applicable_forbids_evidence() -> None:
    with pytest.raises(InvalidEvaluationResponseError, match="forbids evidence"):
        CriterionEvaluation(
            criterion_id="criterion_eval_001",
            status=CriterionEvaluationStatus.NOT_APPLICABLE,
            reason_code=CriterionEvaluationReason.CALL_CONTEXT_NOT_APPLICABLE,
            evidence_spans=(
                TranscriptEvidenceSpan(
                    source_segment_index=0,
                    speaker_label="SPEAKER_00",
                    speaker_role=SpeakerRole.SELLER,
                ),
            ),
        )


def test_insufficient_forbids_absence_evidence() -> None:
    with pytest.raises(InvalidEvaluationResponseError, match="forbids absence evidence"):
        CriterionEvaluation(
            criterion_id="criterion_eval_001",
            status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
            reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
            absence_evidence=AbsenceEvidence(
                scope_start_seconds=0.0,
                scope_end_seconds=1.0,
                speaker_role=None,
                reason_code=AbsenceEvidenceReason.EXPECTED_BEHAVIOR_NOT_OBSERVED,
                reviewed_segment_indexes=(0,),
            ),
        )


def test_scored_transcript_and_absence_cannot_coexist(
    seller_span: TranscriptEvidenceSpan,
) -> None:
    with pytest.raises(InvalidEvaluationResponseError, match="exactly one evidence form"):
        CriterionEvaluation(
            criterion_id="criterion_eval_001",
            status=CriterionEvaluationStatus.SCORED,
            reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
            score=1.0,
            score_level_label="yes",
            evidence_spans=(seller_span,),
            absence_evidence=AbsenceEvidence(
                scope_start_seconds=0.0,
                scope_end_seconds=1.0,
                speaker_role=SpeakerRole.SELLER,
                reason_code=AbsenceEvidenceReason.EXPECTED_BEHAVIOR_NOT_OBSERVED,
                reviewed_segment_indexes=(0,),
            ),
        )


def test_human_review_boolean_reason_consistency() -> None:
    with pytest.raises(InvalidEvaluationResponseError, match="required when human_review_required"):
        CriterionEvaluation(
            criterion_id="criterion_eval_001",
            status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
            reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
            human_review_required=True,
        )
    with pytest.raises(InvalidEvaluationResponseError, match="must be absent"):
        CriterionEvaluation(
            criterion_id="criterion_eval_001",
            status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
            reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
            human_review_required=False,
            human_review_reason=HumanReviewReason.PROVIDER_UNCERTAINTY,
        )


def test_absence_reviewed_segments_required_and_ordered() -> None:
    with pytest.raises(InvalidEvaluationResponseError, match="at least one"):
        AbsenceEvidence(
            scope_start_seconds=0.0,
            scope_end_seconds=1.0,
            speaker_role=None,
            reason_code=AbsenceEvidenceReason.EXPECTED_BEHAVIOR_NOT_OBSERVED,
            reviewed_segment_indexes=(),
        )


def test_evidence_span_word_range_semantics() -> None:
    with pytest.raises(InvalidEvaluationResponseError, match="provided together"):
        TranscriptEvidenceSpan(
            source_segment_index=0,
            source_word_start_index=0,
            speaker_label="SPEAKER_00",
            speaker_role=SpeakerRole.SELLER,
        )


def test_criterion_evaluation_repr_has_no_transcript_or_rubric_text(
    seller_span: TranscriptEvidenceSpan,
) -> None:
    criterion_eval = CriterionEvaluation(
        criterion_id="criterion_eval_001",
        status=CriterionEvaluationStatus.SCORED,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
        score=1.0,
        score_level_label="yes",
        evidence_spans=(seller_span,),
    )
    rendered = repr(criterion_eval)
    assert "SECRET_EVAL_SEGMENT" not in rendered
    assert "SECRET_RUBRIC" not in rendered


def test_quality_flag_mutual_exclusion_all_scored_vs_partial(
    seller_span: TranscriptEvidenceSpan,
) -> None:
    scored = CriterionEvaluation(
        criterion_id="criterion_eval_001",
        status=CriterionEvaluationStatus.SCORED,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
        score=1.0,
        score_level_label="yes",
        evidence_spans=(seller_span,),
    )
    with pytest.raises(
        InvalidEvaluationResponseError,
        match=r"PARTIAL_EVALUATION|mutually exclusive",
    ):
        CallEvaluationResult(
            call_id="call-eval-1",
            rubric_id="rubric_eval_001",
            rubric_version="1.0.0",
            provider_name="fake_eval",
            model_name="fake_eval_v1",
            criterion_evaluations=(scored,),
            quality_flags=(
                EvaluationQualityFlag.ALL_CRITERIA_SCORED,
                EvaluationQualityFlag.PARTIAL_EVALUATION,
            ),
        )


def test_call_evaluation_result_has_expected_properties() -> None:
    assert {field_obj.name for field_obj in fields(CallEvaluationResult)} >= {
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "criterion_evaluations",
    }
