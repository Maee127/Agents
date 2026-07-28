"""Shared fixtures for persistence unit tests."""

from __future__ import annotations

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
    AlignmentResult,
    AlignmentStatus,
    SpeakerAttributedSegment,
)
from sales_call_agent.diarization.models import DiarizationResult, SpeakerTurn
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
from sales_call_agent.persistence.keys import EvaluationKey
from sales_call_agent.speaker_identity.models import (
    RoleAssignmentQualityFlag,
    RoleAssignmentResult,
    RoleAssignmentStatus,
    RoleDecisionReason,
    SpeakerRole,
    SpeakerRoleAssignment,
)
from sales_call_agent.transcription.models import TranscriptionResult, TranscriptSegment


@pytest.fixture
def call() -> Call:
    metadata = CallMetadata(
        call_id="call-abc123def4567890",
        seller_number="SECRET_SELLER_NUMBER",
        source_type=SourceType.RECORDER_APP,
        call_timestamp=datetime(2026, 7, 28, tzinfo=UTC),
        duration_seconds=30.0,
        counterparty_phone="SECRET_COUNTERPARTY_PHONE",
        original_filename="SECRET_ORIGINAL_FILENAME.mp3",
        audio_channels=AudioChannels.MONO,
        storage_path="C:\\SECRET\\AUDIO.mp3",
    )
    audio = AudioAsset(
        storage_path="C:\\SECRET\\AUDIO.mp3",
        audio_channels=AudioChannels.MONO,
        content_hash="a" * 64,
    )
    return Call(metadata=metadata, audio=audio, status=CallProcessingStatus.RECEIVED)


@pytest.fixture
def transcription_result(call: Call) -> TranscriptionResult:
    return TranscriptionResult(
        call_id=call.call_id,
        full_text="SECRET_TRANSCRIPT_TEXT",
        segments=(
            TranscriptSegment(
                text="hello",
                start_seconds=0.0,
                end_seconds=1.0,
            ),
        ),
        provider_name="provider_alpha",
        model_name="model_alpha",
    )


@pytest.fixture
def diarization_result(call: Call) -> DiarizationResult:
    return DiarizationResult(
        call_id=call.call_id,
        turns=(
            SpeakerTurn(speaker_label="SPEAKER_00", start_seconds=0.0, end_seconds=1.0),
            SpeakerTurn(speaker_label="SPEAKER_01", start_seconds=1.0, end_seconds=2.0),
        ),
        provider_name="provider_diar",
        model_name="model_diar",
    )


@pytest.fixture
def alignment_result(call: Call) -> AlignmentResult:
    return AlignmentResult(
        call_id=call.call_id,
        segments=(
            SpeakerAttributedSegment(
                source_segment_index=0,
                text="SECRET_SEGMENT_TEXT",
                start_seconds=0.0,
                end_seconds=1.0,
                speaker_label="SPEAKER_00",
                status=AlignmentStatus.ASSIGNED,
                alignment_method=AlignmentMethod.SEGMENT_LEVEL,
            ),
        ),
    )


@pytest.fixture
def role_assignment_result(call: Call) -> RoleAssignmentResult:
    return RoleAssignmentResult(
        call_id=call.call_id,
        assignments=(
            SpeakerRoleAssignment(
                speaker_label="SPEAKER_00",
                role=SpeakerRole.SELLER,
                status=RoleAssignmentStatus.ASSIGNED,
                reason_code=RoleDecisionReason.STRONG_EVIDENCE,
                supporting_evidence_ids=("EVID001",),
            ),
            SpeakerRoleAssignment(
                speaker_label="SPEAKER_01",
                role=SpeakerRole.CUSTOMER,
                status=RoleAssignmentStatus.ASSIGNED,
                reason_code=RoleDecisionReason.STRONG_EVIDENCE,
                supporting_evidence_ids=("EVID002",),
            ),
        ),
        quality_flags=(RoleAssignmentQualityFlag.MULTI_PARTY_CALL,),
    )


@pytest.fixture
def knowledge_source() -> KnowledgeSource:
    return KnowledgeSource(
        source_id="source_001",
        title="SECRET_SOURCE_TITLE",
        source_type=KnowledgeSourceType.BOOK,
        status=KnowledgeSourceStatus.DRAFT,
        language="en",
        content_hash="b" * 64,
        version="1.0.0",
    )


@pytest.fixture
def knowledge_sections() -> tuple[KnowledgeSection, ...]:
    return (
        KnowledgeSection(
            section_id="section_001",
            source_id="source_001",
            heading="SECRET_HEADING_1",
            text="SECRET_SOURCE_TEXT_1",
            ordinal=1,
            content_hash="c" * 64,
        ),
        KnowledgeSection(
            section_id="section_002",
            source_id="source_001",
            heading="SECRET_HEADING_2",
            text="SECRET_SOURCE_TEXT_2",
            ordinal=2,
            content_hash="d" * 64,
        ),
    )


@pytest.fixture
def rubric() -> SalesRubric:
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
        name="SECRET_RUBRIC_CRITERION",
        definition="SECRET_RUBRIC_DEFINITION",
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
        name="SECRET_RUBRIC_NAME",
        version="1.0.0",
        description="SECRET_RUBRIC_DESCRIPTION",
        status=RubricStatus.DRAFT,
        criteria=(criterion,),
    )


@pytest.fixture
def evaluation_result(call: Call, rubric: SalesRubric) -> CallEvaluationResult:
    return CallEvaluationResult(
        call_id=call.call_id,
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


@pytest.fixture
def evaluation_key(call: Call, rubric: SalesRubric) -> EvaluationKey:
    return EvaluationKey(
        call_id=call.call_id,
        rubric_id=rubric.rubric_id,
        rubric_version=rubric.version,
        provider_name="provider_eval",
        model_name="model_eval",
    )


@pytest.fixture
def call_score_result(call: Call, rubric: SalesRubric) -> CallScoreResult:
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
        call_id=call.call_id,
        rubric_id=rubric.rubric_id,
        rubric_version=rubric.version,
        config=AggregationConfig(),
        criterion_contributions=(contribution,),
        weighted_performance_score=1.0,
        scored_weight_coverage=1.0,
        scored_criterion_coverage=1.0,
        publication_status=CallScorePublicationStatus.PUBLISHABLE,
        quality_flags=(AggregationQualityFlag.FULLY_SCORED_APPLICABLE_RUBRIC,),
    )
