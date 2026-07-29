"""Contract tests for immutable orchestration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from sales_call_agent.orchestration.exceptions import PipelinePrerequisiteError
from sales_call_agent.orchestration.models import (
    CANONICAL_STAGE_ORDER,
    NormalizedAudioReference,
    PipelineFailureReason,
    PipelineRetryClassification,
    PipelineStage,
    PipelineStageOutcome,
    PipelineStageOutcomeStatus,
    PipelineTarget,
    RunCallPipelineRequest,
    RunCallPipelineResult,
    required_stages,
    target_final_stage,
)
from sales_call_agent.persistence.keys import CallScoreKey, EvaluationKey


def _outcomes(target: PipelineTarget) -> tuple[PipelineStageOutcome, ...]:
    return tuple(
        PipelineStageOutcome(stage=stage, status=PipelineStageOutcomeStatus.EXECUTED)
        for stage in required_stages(target)
    )


def _evaluation_key() -> EvaluationKey:
    return EvaluationKey(
        call_id="call-models-001",
        rubric_id="rubric-models-001",
        rubric_version="1.0.0",
        provider_name="fake_evaluator",
        model_name="fake_eval_v1",
    )


def test_stage_order_and_target_mapping_are_canonical() -> None:
    assert CANONICAL_STAGE_ORDER == (
        PipelineStage.TRANSCRIPTION,
        PipelineStage.DIARIZATION,
        PipelineStage.ALIGNMENT,
        PipelineStage.ROLE_ASSIGNMENT,
        PipelineStage.EVALUATION,
        PipelineStage.AGGREGATION,
    )
    assert target_final_stage(PipelineTarget.ROLE_ASSIGNMENT) is PipelineStage.ROLE_ASSIGNMENT
    assert target_final_stage(PipelineTarget.EVALUATION) is PipelineStage.EVALUATION
    assert target_final_stage(PipelineTarget.AGGREGATION) is PipelineStage.AGGREGATION
    assert required_stages(PipelineTarget.EVALUATION) == CANONICAL_STAGE_ORDER[:5]


@pytest.mark.parametrize(
    ("target", "has_evaluation", "has_score"),
    [
        (PipelineTarget.ROLE_ASSIGNMENT, False, False),
        (PipelineTarget.EVALUATION, True, False),
        (PipelineTarget.AGGREGATION, True, True),
    ],
)
def test_result_key_invariants_per_target(
    target: PipelineTarget, has_evaluation: bool, has_score: bool
) -> None:
    evaluation_key = _evaluation_key() if has_evaluation else None
    score_key = (
        CallScoreKey(evaluation_key=evaluation_key, aggregation_policy_fingerprint="a" * 64)
        if has_score
        else None
    )
    result = RunCallPipelineResult(
        call_id="call-models-001",
        requested_target=target,
        reached_stage=target_final_stage(target),
        stage_outcomes=_outcomes(target),
        evaluation_key=evaluation_key,
        call_score_key=score_key,
    )
    assert result.evaluation_key is evaluation_key
    assert result.call_score_key is score_key


def test_reached_stage_must_match_target() -> None:
    with pytest.raises(ValueError, match="reached_stage"):
        RunCallPipelineResult(
            call_id="call-models-001",
            requested_target=PipelineTarget.ROLE_ASSIGNMENT,
            reached_stage=PipelineStage.EVALUATION,
            stage_outcomes=_outcomes(PipelineTarget.ROLE_ASSIGNMENT),
        )


def test_normalized_audio_reference_hides_path_from_repr() -> None:
    reference = NormalizedAudioReference(
        storage_path=Path("normalized/SECRET_SHOULD_NOT_LEAK.asr.wav"),
        content_hash="hash-001",
    )
    assert "SECRET_SHOULD_NOT_LEAK" not in repr(reference)
    assert "hash-001" in repr(reference)


def test_role_assignment_rejects_rubric_fields_and_evaluation_requires_them() -> None:
    with pytest.raises(ValueError, match="rubric fields"):
        RunCallPipelineRequest(
            call_id="call-models-001",
            target=PipelineTarget.ROLE_ASSIGNMENT,
            rubric_id="rubric-models-001",
            rubric_version="1.0.0",
        )
    with pytest.raises(ValueError, match="rubric_id and rubric_version"):
        RunCallPipelineRequest(call_id="call-models-001", target=PipelineTarget.EVALUATION)


def test_exception_repr_excludes_sensitive_message() -> None:
    error = PipelinePrerequisiteError(
        "SECRET transcript or path",
        reason_code=PipelineFailureReason.MISSING_CALL,
        retry_classification=PipelineRetryClassification.NON_RETRYABLE,
    )
    assert "SECRET" not in repr(error)
