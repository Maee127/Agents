"""Unit tests for evaluation provider runner boundary validation."""

from __future__ import annotations

import pytest

from sales_call_agent.evaluation.exceptions import InvalidEvaluationResponseError
from sales_call_agent.evaluation.models import (
    AbsenceEvidence,
    AbsenceEvidenceReason,
    CallEvaluationResult,
    CriterionEvaluation,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationQualityFlag,
    EvaluationRequest,
    HumanReviewReason,
    TranscriptEvidenceSpan,
)
from sales_call_agent.evaluation.provider import run_evaluation
from sales_call_agent.speaker_identity.models import SpeakerRole


class _StaticProvider:
    def __init__(self, result: CallEvaluationResult) -> None:
        self._result = result
        self._provider_name = result.provider_name
        self._model_name = result.model_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def evaluate(self, request: EvaluationRequest) -> CallEvaluationResult:
        return self._result


def _scored_eval(criterion_id: str, span: TranscriptEvidenceSpan) -> CriterionEvaluation:
    return CriterionEvaluation(
        criterion_id=criterion_id,
        status=CriterionEvaluationStatus.SCORED,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
        score=1.0,
        score_level_label="yes",
        evidence_spans=(span,),
    )


def test_runner_validates_criterion_coverage_and_order(
    evaluation_request: EvaluationRequest,
    seller_span: TranscriptEvidenceSpan,
    customer_span: TranscriptEvidenceSpan,
) -> None:
    result = CallEvaluationResult(
        call_id=evaluation_request.call_id,
        rubric_id=evaluation_request.rubric.rubric_id,
        rubric_version=evaluation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_eval_v1",
        criterion_evaluations=(
            _scored_eval("criterion_eval_002", customer_span),
            _scored_eval("criterion_eval_001", seller_span),
        ),
        quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
    )
    with pytest.raises(InvalidEvaluationResponseError, match="in order"):
        run_evaluation(_StaticProvider(result), evaluation_request)


def test_runner_rejects_evidence_role_contradiction(
    evaluation_request: EvaluationRequest,
    customer_span: TranscriptEvidenceSpan,
) -> None:
    bad_span = TranscriptEvidenceSpan(
        source_segment_index=1,
        source_word_start_index=0,
        source_word_end_index=1,
        speaker_label="SPEAKER_01",
        speaker_role=SpeakerRole.SELLER,
    )
    result = CallEvaluationResult(
        call_id=evaluation_request.call_id,
        rubric_id=evaluation_request.rubric.rubric_id,
        rubric_version=evaluation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_eval_v1",
        criterion_evaluations=(
            _scored_eval("criterion_eval_001", bad_span),
            _scored_eval("criterion_eval_002", customer_span),
        ),
        quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
    )
    with pytest.raises(InvalidEvaluationResponseError, match="role must match"):
        run_evaluation(_StaticProvider(result), evaluation_request)


def test_runner_rejects_cross_speaker_word_range(
    evaluation_request: EvaluationRequest,
    customer_span: TranscriptEvidenceSpan,
) -> None:
    crossing_span = TranscriptEvidenceSpan(
        source_segment_index=0,
        source_word_start_index=0,
        source_word_end_index=1,
        speaker_label="SPEAKER_01",
        speaker_role=SpeakerRole.CUSTOMER,
    )
    result = CallEvaluationResult(
        call_id=evaluation_request.call_id,
        rubric_id=evaluation_request.rubric.rubric_id,
        rubric_version=evaluation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_eval_v1",
        criterion_evaluations=(
            _scored_eval("criterion_eval_001", crossing_span),
            _scored_eval("criterion_eval_002", customer_span),
        ),
        quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
    )
    with pytest.raises(InvalidEvaluationResponseError, match="must not cross speakers"):
        run_evaluation(_StaticProvider(result), evaluation_request)


def test_runner_validates_word_indexes_as_source_indexes(
    evaluation_request: EvaluationRequest,
    customer_span: TranscriptEvidenceSpan,
) -> None:
    invalid_source_index_span = TranscriptEvidenceSpan(
        source_segment_index=0,
        source_word_start_index=2,
        source_word_end_index=2,
        speaker_label="SPEAKER_00",
        speaker_role=SpeakerRole.SELLER,
    )
    result = CallEvaluationResult(
        call_id=evaluation_request.call_id,
        rubric_id=evaluation_request.rubric.rubric_id,
        rubric_version=evaluation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_eval_v1",
        criterion_evaluations=(
            _scored_eval("criterion_eval_001", invalid_source_index_span),
            _scored_eval("criterion_eval_002", customer_span),
        ),
        quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
    )
    with pytest.raises(InvalidEvaluationResponseError, match="source_word_index"):
        run_evaluation(_StaticProvider(result), evaluation_request)


def test_runner_enforces_rubric_required_review_reason(
    evaluation_request: EvaluationRequest,
    seller_span: TranscriptEvidenceSpan,
    customer_span: TranscriptEvidenceSpan,
) -> None:
    result = CallEvaluationResult(
        call_id=evaluation_request.call_id,
        rubric_id=evaluation_request.rubric.rubric_id,
        rubric_version=evaluation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_eval_v1",
        criterion_evaluations=(
            _scored_eval("criterion_eval_001", seller_span),
            CriterionEvaluation(
                criterion_id="criterion_eval_002",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=1.0,
                score_level_label="yes",
                evidence_spans=(seller_span, customer_span),
                human_review_required=False,
            ),
        ),
        quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
    )
    with pytest.raises(InvalidEvaluationResponseError, match="requiring human review"):
        run_evaluation(_StaticProvider(result), evaluation_request)


def test_runner_validates_absence_scope_intersection(
    evaluation_request: EvaluationRequest,
    seller_span: TranscriptEvidenceSpan,
) -> None:
    result = CallEvaluationResult(
        call_id=evaluation_request.call_id,
        rubric_id=evaluation_request.rubric.rubric_id,
        rubric_version=evaluation_request.rubric.version,
        provider_name="fake_eval",
        model_name="fake_eval_v1",
        criterion_evaluations=(
            _scored_eval("criterion_eval_001", seller_span),
            CriterionEvaluation(
                criterion_id="criterion_eval_002",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_ABSENCE_EVIDENCE,
                score=1.0,
                score_level_label="yes",
                absence_evidence=AbsenceEvidence(
                    scope_start_seconds=3.0,
                    scope_end_seconds=4.0,
                    speaker_role=SpeakerRole.CUSTOMER,
                    reason_code=AbsenceEvidenceReason.EXPECTED_BEHAVIOR_NOT_OBSERVED,
                    reviewed_segment_indexes=(1,),
                ),
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
        ),
        quality_flags=(
            EvaluationQualityFlag.ALL_CRITERIA_SCORED,
            EvaluationQualityFlag.ABSENCE_EVIDENCE_USED,
            EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED,
        ),
    )
    with pytest.raises(InvalidEvaluationResponseError, match="intersect absence scope"):
        run_evaluation(_StaticProvider(result), evaluation_request)


def test_runner_rejects_unsafe_provider_model_identity(
    evaluation_request: EvaluationRequest,
    seller_span: TranscriptEvidenceSpan,
    customer_span: TranscriptEvidenceSpan,
) -> None:
    with pytest.raises(
        InvalidEvaluationResponseError,
        match=r"safe identifier|path-like",
    ):
        CallEvaluationResult(
            call_id=evaluation_request.call_id,
            rubric_id=evaluation_request.rubric.rubric_id,
            rubric_version=evaluation_request.rubric.version,
            provider_name="fake/eval",
            model_name="C:/local/model",
            criterion_evaluations=(
                _scored_eval("criterion_eval_001", seller_span),
                _scored_eval("criterion_eval_002", customer_span),
            ),
            quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
        )
