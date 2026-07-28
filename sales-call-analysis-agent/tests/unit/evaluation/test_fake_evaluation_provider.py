"""Unit tests for deterministic fake evaluation provider."""

from __future__ import annotations

import pytest

from sales_call_agent.evaluation.exceptions import (
    EvaluationProviderUnavailableError,
    EvaluationRequestFailedError,
    EvaluationTimeoutError,
    InvalidEvaluationResponseError,
)
from sales_call_agent.evaluation.fake import (
    DeterministicFakeEvaluationProvider,
    FakeCriterionOutcome,
    FakeEvaluationMode,
)
from sales_call_agent.evaluation.models import (
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationQualityFlag,
    EvaluationRequest,
    HumanReviewReason,
    TranscriptEvidenceSpan,
)
from sales_call_agent.evaluation.provider import run_evaluation
from sales_call_agent.speaker_identity.models import SpeakerRole


def test_fake_mapping_immutable_against_external_mutation(
    evaluation_request: EvaluationRequest,
) -> None:
    mutable: dict[str, FakeCriterionOutcome] = {}
    provider = DeterministicFakeEvaluationProvider(outcomes=mutable)
    mutable["criterion_eval_001"] = FakeCriterionOutcome(
        criterion_id="criterion_eval_001",
        status=CriterionEvaluationStatus.SCORED,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
        evidence_spans=(
            TranscriptEvidenceSpan(
                source_segment_index=0,
                source_word_start_index=0,
                source_word_end_index=1,
                speaker_label="SPEAKER_00",
                speaker_role=SpeakerRole.SELLER,
            ),
        ),
    )
    result = run_evaluation(provider, evaluation_request)
    assert all(
        item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
        for item in result.criterion_evaluations
    )


def test_fake_does_not_invent_evidence(evaluation_request: EvaluationRequest) -> None:
    provider = DeterministicFakeEvaluationProvider()
    result = run_evaluation(provider, evaluation_request)
    assert all(
        item.reason_code is CriterionEvaluationReason.NO_VALID_EVIDENCE
        for item in result.criterion_evaluations
    )


def test_fake_all_scored_with_explicit_outcomes(evaluation_request: EvaluationRequest) -> None:
    provider = DeterministicFakeEvaluationProvider(
        outcomes={
            "criterion_eval_001": FakeCriterionOutcome(
                criterion_id="criterion_eval_001",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=0,
                        source_word_start_index=0,
                        source_word_end_index=1,
                        speaker_label="SPEAKER_00",
                        speaker_role=SpeakerRole.SELLER,
                    ),
                ),
            ),
            "criterion_eval_002": FakeCriterionOutcome(
                criterion_id="criterion_eval_002",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=0,
                        source_word_start_index=0,
                        source_word_end_index=1,
                        speaker_label="SPEAKER_00",
                        speaker_role=SpeakerRole.SELLER,
                    ),
                    TranscriptEvidenceSpan(
                        source_segment_index=1,
                        source_word_start_index=0,
                        source_word_end_index=1,
                        speaker_label="SPEAKER_01",
                        speaker_role=SpeakerRole.CUSTOMER,
                    ),
                ),
                human_review_required=True,
                human_review_reason=HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW,
            ),
        }
    )
    result = run_evaluation(provider, evaluation_request)
    assert result.scored_count == 2
    assert EvaluationQualityFlag.ALL_CRITERIA_SCORED in result.quality_flags


@pytest.mark.parametrize(
    ("mode", "error_type"),
    [
        (FakeEvaluationMode.PROVIDER_UNAVAILABLE, EvaluationProviderUnavailableError),
        (FakeEvaluationMode.REQUEST_FAILED, EvaluationRequestFailedError),
        (FakeEvaluationMode.TIMEOUT, EvaluationTimeoutError),
    ],
)
def test_fake_operational_errors(
    evaluation_request: EvaluationRequest,
    mode: FakeEvaluationMode,
    error_type: type[Exception],
) -> None:
    provider = DeterministicFakeEvaluationProvider(mode=mode)
    with pytest.raises(error_type):
        run_evaluation(provider, evaluation_request)


@pytest.mark.parametrize(
    "mode",
    [
        FakeEvaluationMode.MISSING_CRITERION,
        FakeEvaluationMode.EXTRA_CRITERION,
        FakeEvaluationMode.INVALID_SCORE,
        FakeEvaluationMode.IDENTITY_MISMATCH,
        FakeEvaluationMode.MALFORMED_EVIDENCE,
    ],
)
def test_fake_invalid_response_modes_rejected(
    evaluation_request: EvaluationRequest,
    mode: FakeEvaluationMode,
) -> None:
    provider = DeterministicFakeEvaluationProvider(mode=mode)
    with pytest.raises(InvalidEvaluationResponseError):
        run_evaluation(provider, evaluation_request)


def test_fake_repeated_results_are_equal(evaluation_request: EvaluationRequest) -> None:
    provider = DeterministicFakeEvaluationProvider()
    first = run_evaluation(provider, evaluation_request)
    second = run_evaluation(provider, evaluation_request)
    assert first == second
