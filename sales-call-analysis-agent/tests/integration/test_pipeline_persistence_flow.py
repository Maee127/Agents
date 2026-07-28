"""Integration-style shared-store persistence flow test."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from sales_call_agent.aggregation.models import (
    AggregationConfig,
    AggregationQualityFlag,
    CallScorePublicationStatus,
    CallScoreResult,
    CriterionScoreContribution,
)
from sales_call_agent.alignment.models import (
    AlignmentMethod,
    AlignmentQualityFlag,
    AlignmentResult,
    AlignmentStatus,
    SpeakerAttributedSegment,
    SpeakerCandidate,
)
from sales_call_agent.diarization.models import (
    DiarizationQualityFlag,
    DiarizationResult,
    SpeakerTurn,
)
from sales_call_agent.domain.models import (
    AudioAsset,
    AudioChannels,
    Call,
    CallMetadata,
    CallProcessingStatus,
    SourceType,
)
from sales_call_agent.evaluation.models import (
    CallEvaluationResult,
    CriterionEvaluation,
    CriterionEvaluationReason,
    CriterionEvaluationStatus,
    EvaluationQualityFlag,
    TranscriptEvidenceSpan,
)
from sales_call_agent.knowledge.models import (
    CriterionOrigin,
    EvidenceRequirement,
    KnowledgeSection,
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    RubricCriterion,
    RubricCriterionCategory,
    RubricScoreLevel,
    RubricScoringScale,
    RubricStatus,
    SalesRubric,
)
from sales_call_agent.persistence.exceptions import RecordNotFoundError, StaleRecordVersionError
from sales_call_agent.persistence.fake import InMemoryPersistenceStore, InMemoryUnitOfWork
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentQualityFlag,
    RoleAssignmentResult,
    RoleAssignmentStatus,
    RoleDecisionReason,
    SpeakerRole,
    SpeakerRoleAssignment,
)
from sales_call_agent.transcription.models import TranscriptionResult, TranscriptSegment


def test_pipeline_persistence_flow() -> None:
    call = _build_call()
    transcription_result = _build_transcription(call.call_id)
    diarization_result = _build_diarization(call.call_id)
    alignment_result = _build_alignment(call.call_id)
    role_assignment_result = _build_roles(call.call_id)
    knowledge_source = _build_source()
    knowledge_sections = _build_sections()
    rubric = _build_rubric()
    evaluation_result = _build_evaluation(call.call_id, rubric)
    call_score_result = _build_score(call.call_id, rubric.rubric_id, rubric.version)

    store = InMemoryPersistenceStore()
    writer = InMemoryUnitOfWork(store=store)
    reader_before_commit = InMemoryUnitOfWork(store=store)

    writer.calls.add(call)
    writer.processing_results.add_transcription(transcription_result)
    writer.processing_results.add_diarization(diarization_result)
    writer.processing_results.add_alignment(alignment_result)
    writer.processing_results.add_role_assignment(role_assignment_result)
    writer.knowledge.add_source(knowledge_source)
    writer.knowledge.add_sections("source_001", knowledge_sections)
    writer.rubrics.add(rubric)
    writer.rubrics.update_status(
        "rubric_001",
        "1.0.0",
        status=RubricStatus.APPROVED,
        expected_revision=1,
    )
    eval_key = writer.evaluations.add(evaluation_result)
    writer.call_scores.add(call_score_result, evaluation_key=eval_key)

    with pytest.raises(RecordNotFoundError):
        reader_before_commit.calls.get(call.call_id)  # type: ignore[attr-defined]

    writer.commit()

    fresh_reader = InMemoryUnitOfWork(store=store)
    assert fresh_reader.calls.get(call.call_id).value == call  # type: ignore[attr-defined]
    assert (
        fresh_reader.processing_results.get_transcription(call.call_id) == transcription_result  # type: ignore[attr-defined]
    )
    assert fresh_reader.evaluations.get(eval_key) == evaluation_result  # type: ignore[comparison-overlap]
    assert len(fresh_reader.call_scores.list_for_evaluation(eval_key)) == 1

    assert "SECRET" not in repr(store)
    assert "SECRET" not in repr(fresh_reader)

    stale_writer = InMemoryUnitOfWork(store=store)
    concurrent_writer = InMemoryUnitOfWork(store=store)
    stale_writer.calls.update(
        replace(call, status=CallProcessingStatus.VALIDATED),
        expected_revision=1,
    )
    stale_writer.commit()
    concurrent_writer.calls.update(
        replace(call, status=CallProcessingStatus.FAILED),
        expected_revision=1,
    )
    with pytest.raises(StaleRecordVersionError):
        concurrent_writer.commit()


def _build_call() -> Call:
    metadata = CallMetadata(
        call_id="call-int-001",
        seller_number="SECRET_SELLER",
        source_type=SourceType.RECORDER_APP,
        call_timestamp=datetime(2026, 7, 28, tzinfo=UTC),
        duration_seconds=20.0,
        counterparty_phone="SECRET_COUNTERPARTY",
        original_filename="SECRET_AUDIO.mp3",
        audio_channels=AudioChannels.MONO,
        storage_path="C:\\SECRET\\int.mp3",
    )
    audio = AudioAsset(
        storage_path="C:\\SECRET\\int.mp3",
        audio_channels=AudioChannels.MONO,
        content_hash="f" * 64,
    )
    return Call(metadata=metadata, audio=audio)


def _build_transcription(call_id: str) -> TranscriptionResult:
    return TranscriptionResult(
        call_id=call_id,
        full_text="SECRET_TRANSCRIPT",
        segments=(TranscriptSegment(text="hi", start_seconds=0.0, end_seconds=1.0),),
        provider_name="provider_eval",
        model_name="model_eval",
    )


def _build_diarization(call_id: str) -> DiarizationResult:
    return DiarizationResult(
        call_id=call_id,
        turns=(SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),),
        provider_name="provider_diar",
        model_name="model_diar",
        quality_flags=(DiarizationQualityFlag.SINGLE_SPEAKER_DETECTED,),
    )


def _build_alignment(call_id: str) -> AlignmentResult:
    return AlignmentResult(
        call_id=call_id,
        segments=(
            SpeakerAttributedSegment(
                source_segment_index=0,
                text="SECRET_ALIGNMENT",
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
        ),
        quality_flags=(AlignmentQualityFlag.SEGMENT_LEVEL_FALLBACK_USED,),
    )


def _build_roles(call_id: str) -> RoleAssignmentResult:
    return RoleAssignmentResult(
        call_id=call_id,
        assignments=(
            SpeakerRoleAssignment(
                speaker_label="SPEAKER_00",
                role=SpeakerRole.SELLER,
                status=RoleAssignmentStatus.ASSIGNED,
                reason_code=RoleDecisionReason.STRONG_EVIDENCE,
                supporting_evidence_ids=("EV1",),
            ),
        ),
        quality_flags=(RoleAssignmentQualityFlag.SINGLE_SPEAKER_CALL,),
    )


def _build_source() -> KnowledgeSource:
    return KnowledgeSource(
        source_id="source_001",
        title="SECRET_SOURCE_TITLE",
        source_type=KnowledgeSourceType.BOOK,
        status=KnowledgeSourceStatus.DRAFT,
        language="en",
        content_hash="a" * 64,
        version="1.0.0",
    )


def _build_sections() -> tuple[KnowledgeSection, ...]:
    return (
        KnowledgeSection(
            section_id="section_001",
            source_id="source_001",
            heading="SECRET_H",
            text="SECRET_T",
            ordinal=1,
            content_hash="b" * 64,
        ),
    )


def _build_rubric() -> SalesRubric:
    scale = RubricScoringScale(
        scale_id="scale_001",
        name="binary",
        levels=(
            RubricScoreLevel(score=0.0, label="no", description="no"),
            RubricScoreLevel(score=1.0, label="yes", description="yes"),
        ),
    )
    criterion = RubricCriterion(
        criterion_id="criterion_001",
        name="SECRET_C",
        definition="SECRET_D",
        positive_guidance="pos",
        negative_guidance="neg",
        category=RubricCriterionCategory.OPENING,
        origin=CriterionOrigin.ORGANIZATION_DEFINED,
        weight=1.0,
        scoring_scale=scale,
        evidence_requirement=EvidenceRequirement(),
    )
    return SalesRubric(
        rubric_id="rubric_001",
        name="SECRET_RUBRIC",
        version="1.0.0",
        description="SECRET_DESC",
        status=RubricStatus.DRAFT,
        criteria=(criterion,),
    )


def _build_evaluation(call_id: str, rubric: SalesRubric) -> CallEvaluationResult:
    return CallEvaluationResult(
        call_id=call_id,
        rubric_id=rubric.rubric_id,
        rubric_version=rubric.version,
        provider_name="provider_eval",
        model_name="model_eval",
        criterion_evaluations=(
            CriterionEvaluation(
                criterion_id="criterion_001",
                status=CriterionEvaluationStatus.SCORED,
                reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
                score=1.0,
                score_level_label="yes",
                evidence_spans=(
                    TranscriptEvidenceSpan(
                        source_segment_index=0,
                        speaker_label="SPEAKER_00",
                        speaker_role=SpeakerRole.SELLER,
                    ),
                ),
            ),
        ),
        quality_flags=(EvaluationQualityFlag.ALL_CRITERIA_SCORED,),
    )


def _build_score(call_id: str, rubric_id: str, rubric_version: str) -> CallScoreResult:
    contribution = CriterionScoreContribution(
        criterion_id="criterion_001",
        status=CriterionEvaluationStatus.SCORED,
        criterion_weight=1.0,
        raw_score=1.0,
        normalized_score=1.0,
        weighted_points=1.0,
        human_review_required=False,
        human_review_reason=None,
        reason_code=CriterionEvaluationReason.SUPPORTED_BY_TRANSCRIPT_EVIDENCE,
    )
    return CallScoreResult(
        call_id=call_id,
        rubric_id=rubric_id,
        rubric_version=rubric_version,
        config=AggregationConfig(),
        criterion_contributions=(contribution,),
        weighted_performance_score=1.0,
        scored_weight_coverage=1.0,
        scored_criterion_coverage=1.0,
        publication_status=CallScorePublicationStatus.PUBLISHABLE,
        quality_flags=(AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC,),
    )
