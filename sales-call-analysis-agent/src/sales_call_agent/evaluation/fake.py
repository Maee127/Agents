"""Deterministic fake evaluation provider for tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from sales_call_agent.evaluation.exceptions import (
    EvaluationProviderUnavailableError,
    EvaluationRequestFailedError,
    EvaluationTimeoutError,
    UnsupportedEvaluationConfigurationError,
)
from sales_call_agent.evaluation.models import (
    AbsenceEvidence,
    CallEvaluationResult,
    CriterionEvaluation,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationQualityFlag,
    EvaluationRequest,
    HumanReviewReason,
    TranscriptEvidenceSpan,
)
from sales_call_agent.knowledge.models import RubricScoreLevel
from sales_call_agent.speaker_identity.models import SpeakerRole


class FakeEvaluationMode(StrEnum):
    """Deterministic fake provider behavior mode."""

    NORMAL = "normal"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    REQUEST_FAILED = "request_failed"
    TIMEOUT = "timeout"
    MISSING_CRITERION = "missing_criterion"
    EXTRA_CRITERION = "extra_criterion"
    INVALID_SCORE = "invalid_score"
    IDENTITY_MISMATCH = "identity_mismatch"
    MALFORMED_EVIDENCE = "malformed_evidence"


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeCriterionOutcome:
    """Explicit fake outcome override for one criterion."""

    criterion_id: str
    status: CriterionEvaluationStatus
    reason_code: CriterionEvaluationReason
    score: float | None = None
    evidence_spans: tuple[TranscriptEvidenceSpan, ...] = ()
    absence_evidence: AbsenceEvidence | None = None
    human_review_required: bool = False
    human_review_reason: HumanReviewReason | None = None
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class DeterministicFakeEvaluationProvider:
    """Configurable deterministic fake provider with explicit criterion outcomes."""

    provider_name: str = "fake_evaluator"
    model_name: str = "fake_eval_v1"
    mode: FakeEvaluationMode = FakeEvaluationMode.NORMAL
    outcomes: Mapping[str, FakeCriterionOutcome] = field(default_factory=dict, repr=False)
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_name.strip():
            raise UnsupportedEvaluationConfigurationError("provider_name must not be empty")
        if not self.model_name.strip():
            raise UnsupportedEvaluationConfigurationError("model_name must not be empty")
        if not isinstance(self.mode, FakeEvaluationMode):
            raise UnsupportedEvaluationConfigurationError("mode must be a FakeEvaluationMode")
        copied = {key: value for key, value in self.outcomes.items()}
        for key, value in copied.items():
            if not key.strip():
                raise UnsupportedEvaluationConfigurationError("outcome keys must be non-empty")
            if not isinstance(value, FakeCriterionOutcome):
                raise UnsupportedEvaluationConfigurationError(
                    "outcomes must contain FakeCriterionOutcome values"
                )
            if value.criterion_id != key:
                raise UnsupportedEvaluationConfigurationError(
                    "outcome key must match outcome criterion_id"
                )
        object.__setattr__(self, "outcomes", MappingProxyType(copied))

    def evaluate(self, request: EvaluationRequest) -> CallEvaluationResult:
        if self.mode is FakeEvaluationMode.PROVIDER_UNAVAILABLE:
            raise EvaluationProviderUnavailableError("fake evaluation provider unavailable")
        if self.mode is FakeEvaluationMode.REQUEST_FAILED:
            raise EvaluationRequestFailedError("fake evaluation request failed")
        if self.mode is FakeEvaluationMode.TIMEOUT:
            raise EvaluationTimeoutError("fake evaluation request timed out")

        criterion_evaluations: list[CriterionEvaluation] = []
        for criterion in request.rubric.criteria:
            override = self.outcomes.get(criterion.criterion_id)
            if override is None:
                criterion_evaluations.append(
                    CriterionEvaluation(
                        criterion_id=criterion.criterion_id,
                        status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                        reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
                        human_review_required=criterion.evidence_requirement.human_review_required,
                        human_review_reason=(
                            HumanReviewReason.RUBRIC_REQUIRES_HUMAN_REVIEW
                            if criterion.evidence_requirement.human_review_required
                            else None
                        ),
                    )
                )
                continue

            score = override.score
            if (
                override.status is CriterionEvaluationStatus.SCORED
                and score is None
                and override.evidence_spans
            ):
                score = float(criterion.scoring_scale.levels[0].score)

            label = None
            if score is not None:
                label = _score_label_for(criterion.scoring_scale.levels, score)

            criterion_evaluations.append(
                CriterionEvaluation(
                    criterion_id=override.criterion_id,
                    status=override.status,
                    reason_code=override.reason_code,
                    score=score,
                    score_level_label=label,
                    evidence_spans=override.evidence_spans,
                    absence_evidence=override.absence_evidence,
                    human_review_required=override.human_review_required,
                    human_review_reason=override.human_review_reason,
                    warning_codes=override.warning_codes,
                )
            )

        if self.mode is FakeEvaluationMode.MISSING_CRITERION and criterion_evaluations:
            criterion_evaluations = criterion_evaluations[:-1]
        if self.mode is FakeEvaluationMode.EXTRA_CRITERION:
            criterion_evaluations.append(
                CriterionEvaluation(
                    criterion_id="extra_criterion",
                    status=CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
                    reason_code=CriterionEvaluationReason.NO_VALID_EVIDENCE,
                )
            )
        if self.mode is FakeEvaluationMode.INVALID_SCORE and criterion_evaluations:
            first = criterion_evaluations[0]
            criterion_evaluations[0] = CriterionEvaluation(
                criterion_id=first.criterion_id,
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=999.0,
                score_level_label="invalid",
                evidence_spans=first.evidence_spans
                if first.evidence_spans
                else (
                    TranscriptEvidenceSpan(
                        source_segment_index=0,
                        speaker_label=request.alignment.speaker_labels[0],
                        speaker_role=request.role_assignment.assignments[0].role,
                    ),
                ),
            )
        if self.mode is FakeEvaluationMode.MALFORMED_EVIDENCE and criterion_evaluations:
            first = criterion_evaluations[0]
            criterion_evaluations[0] = CriterionEvaluation(
                criterion_id=first.criterion_id,
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=float(request.rubric.criteria[0].scoring_scale.levels[0].score),
                score_level_label=request.rubric.criteria[0].scoring_scale.levels[0].label,
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=999999,
                        speaker_label=request.alignment.speaker_labels[0],
                        speaker_role=request.role_assignment.assignments[0].role,
                    ),
                ),
            )

        provider_name = self.provider_name
        model_name = self.model_name
        if self.mode is FakeEvaluationMode.IDENTITY_MISMATCH:
            provider_name = f"{provider_name}_mismatch"
            model_name = f"{model_name}_mismatch"

        quality_flags = _derive_quality_flags(criterion_evaluations, self.warning_codes)
        return CallEvaluationResult(
            call_id=request.call_id,
            rubric_id=request.rubric.rubric_id,
            rubric_version=request.rubric.version,
            provider_name=provider_name,
            model_name=model_name,
            criterion_evaluations=tuple(criterion_evaluations),
            quality_flags=quality_flags,
            warning_codes=self.warning_codes,
        )


def _score_label_for(levels: tuple[RubricScoreLevel, ...], score: float) -> str:
    for level in levels:
        if float(level.score) == float(score):
            return level.label
    return "unknown"


def _derive_quality_flags(
    criterion_evaluations: list[CriterionEvaluation],
    warning_codes: tuple[str, ...],
) -> tuple[EvaluationQualityFlag, ...]:
    has_scored = any(
        item.status is CriterionEvaluationStatus.SCORED for item in criterion_evaluations
    )
    has_non_scored = any(
        item.status
        in {
            CriterionEvaluationStatus.NOT_APPLICABLE,
            CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE,
        }
        for item in criterion_evaluations
    )
    all_scored = bool(criterion_evaluations) and not has_non_scored
    flags: set[EvaluationQualityFlag] = set()
    if any(
        item.status is CriterionEvaluationStatus.INSUFFICIENT_EVIDENCE
        for item in criterion_evaluations
    ):
        flags.add(EvaluationQualityFlag.INSUFFICIENT_EVIDENCE_PRESENT)
    if any(
        item.status is CriterionEvaluationStatus.NOT_APPLICABLE for item in criterion_evaluations
    ):
        flags.add(EvaluationQualityFlag.NOT_APPLICABLE_CRITERIA_PRESENT)
    if any(item.human_review_required for item in criterion_evaluations):
        flags.add(EvaluationQualityFlag.HUMAN_REVIEW_REQUIRED)
    if any(item.absence_evidence is not None for item in criterion_evaluations):
        flags.add(EvaluationQualityFlag.ABSENCE_EVIDENCE_USED)
    if any(
        any(span.speaker_role is SpeakerRole.UNKNOWN for span in item.evidence_spans)
        or item.reason_code is CriterionEvaluationReason.SELLER_ROLE_UNRESOLVED
        or item.human_review_reason is HumanReviewReason.AMBIGUOUS_SPEAKER_ROLE
        for item in criterion_evaluations
    ):
        flags.add(EvaluationQualityFlag.UNKNOWN_SPEAKER_ROLES_PRESENT)
    if all_scored:
        flags.add(EvaluationQualityFlag.ALL_CRITERIA_SCORED)
    if has_scored and has_non_scored:
        flags.add(EvaluationQualityFlag.PARTIAL_EVALUATION)
    if warning_codes:
        flags.add(EvaluationQualityFlag.PROVIDER_WARNING)
    return tuple(sorted(flags, key=lambda item: item.value))
