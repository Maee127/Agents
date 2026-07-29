"""SQLAlchemy Core table definitions for the PostgreSQL adapter.

All tables are registered against the shared MetaData singleton.
Import this module (or the package) before using metadata.tables.

Field-parity matrix (domain field → column):
---------------------------------------------
Call / CallMetadata / AudioAsset:
  call_id                    → calls.call_id  (PK)
  seller_number              → calls.seller_number
  source_type                → calls.source_type
  call_timestamp             → calls.call_timestamp
  duration_seconds           → calls.duration_seconds
  counterparty_phone         → calls.counterparty_phone (nullable)
  original_filename          → calls.original_filename
  audio_channels             → calls.audio_channels
  storage_path (metadata)    → calls.storage_path
  storage_path (audio)       → calls.storage_path  (same value, validated in mapper)
  content_hash (audio)       → calls.content_hash
  status                     → calls.status
  revision                   → calls.revision

KnowledgeSource:
  source_id                  → knowledge_sources.source_id  (PK)
  title                      → knowledge_sources.title
  source_type                → knowledge_sources.source_type
  status                     → knowledge_sources.status
  author                     → knowledge_sources.author
  edition                    → knowledge_sources.edition
  publication_year           → knowledge_sources.publication_year
  language                   → knowledge_sources.language
  content_hash               → knowledge_sources.content_hash
  version                    → knowledge_sources.version
  warning_codes              → knowledge_sources.warning_codes (TEXT[])
  revision                   → knowledge_sources.revision

KnowledgeSection:
  section_id                 → knowledge_sections.section_id  (PK)
  source_id                  → knowledge_sections.source_id   (FK)
  heading                    → knowledge_sections.heading
  text                       → knowledge_sections.text
  ordinal                    → knowledge_sections.ordinal
  page_start                 → knowledge_sections.page_start
  page_end                   → knowledge_sections.page_end
  chapter                    → knowledge_sections.chapter
  content_hash               → knowledge_sections.content_hash
  language                   → knowledge_sections.language
  warning_codes              → knowledge_sections.warning_codes (TEXT[])

SalesRubric:
  rubric_id                  → rubrics.rubric_id   (PK part)
  version                    → rubrics.version     (PK part)
  version_major              → rubrics.version_major  (for semver ordering)
  version_minor              → rubrics.version_minor
  version_patch              → rubrics.version_patch
  name                       → rubrics.name
  description                → rubrics.description
  language                   → rubrics.language
  status                     → rubrics.status
  warning_codes              → rubrics.warning_codes (TEXT[])
  revision                   → rubrics.revision

RubricCriterion:
  criterion_id               → rubric_criteria.criterion_id
  rubric_id / version        → rubric_criteria.rubric_id, rubric_version (FK)
  criterion_order            → rubric_criteria.criterion_order
  name                       → rubric_criteria.name
  definition                 → rubric_criteria.definition
  positive_guidance          → rubric_criteria.positive_guidance
  negative_guidance          → rubric_criteria.negative_guidance
  category                   → rubric_criteria.category
  origin                     → rubric_criteria.origin
  weight                     → rubric_criteria.weight
  warning_codes              → rubric_criteria.warning_codes

RubricScoringScale:
  scale_id                   → rubric_scoring_scales.scale_id
  name                       → rubric_scoring_scales.name
  warning_codes              → rubric_scoring_scales.warning_codes

RubricScoreLevel:
  level_order                → rubric_score_levels.level_order
  score                      → rubric_score_levels.score
  label                      → rubric_score_levels.label
  description                → rubric_score_levels.description
  warning_codes              → rubric_score_levels.warning_codes

EvidenceRequirement:
  transcript_evidence_required    → rubric_evidence_requirements.*
  timestamp_required              → rubric_evidence_requirements.*
  minimum_evidence_spans          → rubric_evidence_requirements.*
  seller_role_required            → rubric_evidence_requirements.*
  customer_context_required       → rubric_evidence_requirements.*
  absence_can_be_evidence         → rubric_evidence_requirements.*
  human_review_required           → rubric_evidence_requirements.*

SourceCitation:
  citation_order             → rubric_source_citations.citation_order
  source_id                  → rubric_source_citations.source_id (FK)
  section_id                 → rubric_source_citations.section_id (FK via composite)
  page_start                 → rubric_source_citations.page_start
  page_end                   → rubric_source_citations.page_end
  citation_note_code         → rubric_source_citations.citation_note_code

TranscriptionResult:
  call_id                    → transcription_results.call_id   (PK/FK)
  full_text                  → transcription_results.full_text
  detected_language          → transcription_results.detected_language
  language_confidence        → transcription_results.language_confidence
  provider_name              → transcription_results.provider_name
  model_name                 → transcription_results.model_name
  processing_duration_seconds→ transcription_results.processing_duration_seconds
  provider_confidence        → transcription_results.provider_confidence (JSONB[])
  quality_flags              → transcription_results.quality_flags (TEXT[])
  warning_codes              → transcription_results.warning_codes (TEXT[])

TranscriptSegment:
  [tuple position]           → transcription_segments.segment_order
  text                       → transcription_segments.text
  start_seconds              → transcription_segments.start_seconds
  end_seconds                → transcription_segments.end_seconds
  provider_confidence        → transcription_segments.provider_confidence (JSONB)
  quality_flags              → transcription_segments.quality_flags (TEXT[])
  warning_codes              → transcription_segments.warning_codes (TEXT[])

TranscriptWord:
  [tuple position]           → transcription_words.word_order
  text                       → transcription_words.text
  start_seconds              → transcription_words.start_seconds
  end_seconds                → transcription_words.end_seconds
  provider_confidence        → transcription_words.provider_confidence (JSONB)

DiarizationResult:
  call_id                    → diarization_results.call_id   (PK/FK)
  provider_name              → diarization_results.provider_name
  model_name                 → diarization_results.model_name
  processing_duration_seconds→ diarization_results.processing_duration_seconds
  provider_confidence        → diarization_results.provider_confidence (JSONB)
  quality_flags              → diarization_results.quality_flags (TEXT[])
  warning_codes              → diarization_results.warning_codes (TEXT[])

SpeakerTurn:
  [tuple position]           → diarization_turns.turn_order
  speaker_label              → diarization_turns.speaker_label
  start_seconds              → diarization_turns.start_seconds
  end_seconds                → diarization_turns.end_seconds
  provider_confidence        → diarization_turns.provider_confidence (JSONB)

AlignmentResult:
  call_id                    → alignment_results.call_id  (PK/FK)
  quality_flags              → alignment_results.quality_flags (TEXT[])
  warning_codes              → alignment_results.warning_codes (TEXT[])
  (no provider_name/model — deterministic engine, no provider)

SpeakerAttributedSegment:
  [tuple position]           → alignment_segments.segment_order
  source_segment_index       → alignment_segments.source_segment_index
  text                       → alignment_segments.text
  start_seconds              → alignment_segments.start_seconds
  end_seconds                → alignment_segments.end_seconds
  speaker_label              → alignment_segments.speaker_label
  status                     → alignment_segments.status
  alignment_method           → alignment_segments.alignment_method
  overlapping_speech         → alignment_segments.overlapping_speech
  candidates                 → alignment_segments.candidates (JSONB)

SpeakerAttributedWord:
  [tuple position]           → alignment_words.word_order
  source_word_index          → alignment_words.source_word_index
  text                       → alignment_words.text
  start_seconds              → alignment_words.start_seconds
  end_seconds                → alignment_words.end_seconds
  speaker_label              → alignment_words.speaker_label
  status                     → alignment_words.status
  overlapping_speech         → alignment_words.overlapping_speech
  candidates                 → alignment_words.candidates (JSONB)

RoleAssignmentResult:
  call_id                    → role_assignment_results.call_id  (PK/FK)
  quality_flags              → role_assignment_results.quality_flags (TEXT[])
  warning_codes              → role_assignment_results.warning_codes (TEXT[])

SpeakerRoleAssignment:
  [tuple position]           → role_assignments.assignment_order
  speaker_label              → role_assignments.speaker_label
  role                       → role_assignments.role
  status                     → role_assignments.status
  reason_code                → role_assignments.reason_code
  supporting_evidence_ids    → role_assignments.supporting_evidence_ids (TEXT[])
  conflicting_evidence_ids   → role_assignments.conflicting_evidence_ids (TEXT[])
  warning_codes              → role_assignments.warning_codes (TEXT[])

CallEvaluationResult:
  call_id                    → call_evaluations.call_id  (PK/FK)
  rubric_id                  → call_evaluations.rubric_id (PK, FK to rubrics)
  rubric_version             → call_evaluations.rubric_version (PK)
  provider_name              → call_evaluations.provider_name  (PK)
  model_name                 → call_evaluations.model_name     (PK)
  quality_flags              → call_evaluations.quality_flags (TEXT[])
  warning_codes              → call_evaluations.warning_codes (TEXT[])

CriterionEvaluation:
  [tuple position]           → criterion_evaluations.criterion_order
  criterion_id               → criterion_evaluations.criterion_id
  status                     → criterion_evaluations.status
  reason_code                → criterion_evaluations.reason_code
  score                      → criterion_evaluations.score
  score_level_label          → criterion_evaluations.score_level_label
  human_review_required      → criterion_evaluations.human_review_required
  human_review_reason        → criterion_evaluations.human_review_reason
  warning_codes              → criterion_evaluations.warning_codes (TEXT[])

TranscriptEvidenceSpan:
  [tuple position]           → transcript_evidence_spans.span_order
  source_segment_index       → transcript_evidence_spans.source_segment_index
  source_word_start_index    → transcript_evidence_spans.source_word_start_index
  source_word_end_index      → transcript_evidence_spans.source_word_end_index
  speaker_label              → transcript_evidence_spans.speaker_label
  speaker_role               → transcript_evidence_spans.speaker_role
  warning_codes              → transcript_evidence_spans.warning_codes (TEXT[])

AbsenceEvidence:
  scope_start_seconds        → absence_evidences.scope_start_seconds
  scope_end_seconds          → absence_evidences.scope_end_seconds
  speaker_role               → absence_evidences.speaker_role (nullable)
  reason_code                → absence_evidences.reason_code
  reviewed_segment_indexes   → absence_evidences.reviewed_segment_indexes (INTEGER[])
  warning_codes              → absence_evidences.warning_codes (TEXT[])

CallScoreResult:
  call_id                    → call_scores.call_id  (PK/FK)
  rubric_id                  → call_scores.rubric_id  (PK)
  rubric_version             → call_scores.rubric_version  (PK)
  provider_name (via eval key) → call_scores.provider_name (PK)
  model_name (via eval key)  → call_scores.model_name (PK)
  aggregation_policy_fingerprint → call_scores.aggregation_policy_fingerprint (PK)
  config.minimum_scored_weight_coverage → call_scores.min_scored_weight_coverage
  config.minimum_scored_criterion_coverage → call_scores.min_scored_criterion_coverage
  config.require_no_human_review_for_publish → call_scores.require_no_human_review_for_publish
  weighted_performance_score → call_scores.weighted_performance_score
  scored_weight_coverage     → call_scores.scored_weight_coverage
  scored_criterion_coverage  → call_scores.scored_criterion_coverage
  publication_status         → call_scores.publication_status
  quality_flags              → call_scores.quality_flags (TEXT[])
  warning_codes              → call_scores.warning_codes (TEXT[])

CriterionScoreContribution:
  [tuple position]           → criterion_score_contributions.contribution_order
  criterion_id               → criterion_score_contributions.criterion_id
  status                     → criterion_score_contributions.status
  criterion_weight           → criterion_score_contributions.criterion_weight
  raw_score                  → criterion_score_contributions.raw_score
  normalized_score           → criterion_score_contributions.normalized_score
  weighted_points            → criterion_score_contributions.weighted_points
  human_review_required      → criterion_score_contributions.human_review_required
  human_review_reason        → criterion_score_contributions.human_review_reason
  reason_code                → criterion_score_contributions.reason_code
  warning_codes              → criterion_score_contributions.warning_codes (TEXT[])
"""

from __future__ import annotations

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Double,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import TIMESTAMP as Timestamp
from sqlalchemy import Table

from sales_call_agent.infrastructure.postgres.metadata import metadata

# ---------------------------------------------------------------------------
# calls
# ---------------------------------------------------------------------------
calls = Table(
    "calls",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("status", Text, nullable=False),
    Column("source_type", Text, nullable=False),
    Column("audio_channels", Text, nullable=False),
    Column("call_timestamp", Timestamp(timezone=True), nullable=False),
    Column("duration_seconds", Double, nullable=False),
    Column("seller_number", Text, nullable=False),
    Column("counterparty_phone", Text, nullable=True),
    Column("original_filename", Text, nullable=False),
    Column("storage_path", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("call_id", name="pk_calls"),
    CheckConstraint("revision >= 1", name="ck_calls_revision_positive"),
    CheckConstraint("duration_seconds >= 0", name="ck_calls_duration_non_negative"),
    CheckConstraint(
        "content_hash ~ '^[0-9a-f]{64}$'", name="ck_calls_content_hash_format"
    ),
)

# ---------------------------------------------------------------------------
# knowledge_sources
# ---------------------------------------------------------------------------
knowledge_sources = Table(
    "knowledge_sources",
    metadata,
    Column("source_id", Text, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("title", Text, nullable=False),
    Column("source_type", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("author", Text, nullable=True),
    Column("edition", Text, nullable=True),
    Column("publication_year", Integer, nullable=True),
    Column("language", Text, nullable=False),
    Column("content_hash", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("source_id", name="pk_knowledge_sources"),
    CheckConstraint("revision >= 1", name="ck_knowledge_sources_revision_positive"),
    CheckConstraint(
        "content_hash ~ '^[0-9a-f]{64}$'",
        name="ck_knowledge_sources_content_hash_format",
    ),
    CheckConstraint(
        "publication_year IS NULL OR publication_year > 0",
        name="ck_knowledge_sources_publication_year_positive",
    ),
)

# ---------------------------------------------------------------------------
# knowledge_sections
# ---------------------------------------------------------------------------
knowledge_sections = Table(
    "knowledge_sections",
    metadata,
    Column("section_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("heading", Text, nullable=True),
    Column("text", Text, nullable=False),
    Column("page_start", Integer, nullable=True),
    Column("page_end", Integer, nullable=True),
    Column("chapter", Text, nullable=True),
    Column("content_hash", Text, nullable=False),
    Column("language", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("section_id", name="pk_knowledge_sections"),
    ForeignKeyConstraint(
        ["source_id"],
        ["knowledge_sources.source_id"],
        name="fk_knowledge_sections_source_id_knowledge_sources",
    ),
    UniqueConstraint("source_id", "ordinal", name="uq_knowledge_sections_source_ordinal"),
    UniqueConstraint(
        "source_id", "section_id", name="uq_knowledge_sections_source_section"
    ),
    CheckConstraint("ordinal >= 0", name="ck_knowledge_sections_ordinal_non_negative"),
    CheckConstraint(
        "content_hash ~ '^[0-9a-f]{64}$'",
        name="ck_knowledge_sections_content_hash_format",
    ),
    CheckConstraint(
        "page_start IS NULL OR page_start > 0",
        name="ck_knowledge_sections_page_start_positive",
    ),
    CheckConstraint(
        "page_end IS NULL OR (page_start IS NOT NULL AND page_end >= page_start)",
        name="ck_knowledge_sections_page_range_valid",
    ),
)

# ---------------------------------------------------------------------------
# rubrics
# ---------------------------------------------------------------------------
rubrics = Table(
    "rubrics",
    metadata,
    Column("rubric_id", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("version_major", Integer, nullable=False),
    Column("version_minor", Integer, nullable=False),
    Column("version_patch", Integer, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("language", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("rubric_id", "version", name="pk_rubrics"),
    CheckConstraint("revision >= 1", name="ck_rubrics_revision_positive"),
    CheckConstraint("version_major >= 0", name="ck_rubrics_version_major_non_negative"),
    CheckConstraint("version_minor >= 0", name="ck_rubrics_version_minor_non_negative"),
    CheckConstraint("version_patch >= 0", name="ck_rubrics_version_patch_non_negative"),
)

# ---------------------------------------------------------------------------
# rubric_criteria
# ---------------------------------------------------------------------------
rubric_criteria = Table(
    "rubric_criteria",
    metadata,
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("criterion_order", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("definition", Text, nullable=False),
    Column("positive_guidance", Text, nullable=False),
    Column("negative_guidance", Text, nullable=False),
    Column("category", Text, nullable=False),
    Column("origin", Text, nullable=False),
    Column("weight", Double, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "rubric_id", "rubric_version", "criterion_id", name="pk_rubric_criteria"
    ),
    ForeignKeyConstraint(
        ["rubric_id", "rubric_version"],
        ["rubrics.rubric_id", "rubrics.version"],
        name="fk_rubric_criteria_rubric_id_rubrics",
    ),
    UniqueConstraint(
        "rubric_id",
        "rubric_version",
        "criterion_order",
        name="uq_rubric_criteria_order",
    ),
    CheckConstraint(
        "criterion_order >= 0", name="ck_rubric_criteria_order_non_negative"
    ),
    CheckConstraint("weight > 0", name="ck_rubric_criteria_weight_positive"),
)

# ---------------------------------------------------------------------------
# rubric_scoring_scales
# ---------------------------------------------------------------------------
rubric_scoring_scales = Table(
    "rubric_scoring_scales",
    metadata,
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("scale_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "rubric_id",
        "rubric_version",
        "criterion_id",
        "scale_id",
        name="pk_rubric_scoring_scales",
    ),
    ForeignKeyConstraint(
        ["rubric_id", "rubric_version", "criterion_id"],
        [
            "rubric_criteria.rubric_id",
            "rubric_criteria.rubric_version",
            "rubric_criteria.criterion_id",
        ],
        name="fk_rubric_scoring_scales_criterion_id_rubric_criteria",
    ),
)

# ---------------------------------------------------------------------------
# rubric_score_levels
# ---------------------------------------------------------------------------
rubric_score_levels = Table(
    "rubric_score_levels",
    metadata,
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("scale_id", Text, nullable=False),
    Column("level_order", Integer, nullable=False),
    Column("score", Double, nullable=False),
    Column("label", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "rubric_id",
        "rubric_version",
        "criterion_id",
        "scale_id",
        "level_order",
        name="pk_rubric_score_levels",
    ),
    ForeignKeyConstraint(
        ["rubric_id", "rubric_version", "criterion_id", "scale_id"],
        [
            "rubric_scoring_scales.rubric_id",
            "rubric_scoring_scales.rubric_version",
            "rubric_scoring_scales.criterion_id",
            "rubric_scoring_scales.scale_id",
        ],
        name="fk_rubric_score_levels_scale_id_rubric_scoring_scales",
    ),
    UniqueConstraint(
        "rubric_id",
        "rubric_version",
        "criterion_id",
        "scale_id",
        "score",
        name="uq_rubric_score_levels_score",
    ),
    CheckConstraint("level_order >= 0", name="ck_rubric_score_levels_order_non_negative"),
)

# ---------------------------------------------------------------------------
# rubric_evidence_requirements
# ---------------------------------------------------------------------------
rubric_evidence_requirements = Table(
    "rubric_evidence_requirements",
    metadata,
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("transcript_evidence_required", Boolean, nullable=False, server_default="true"),
    Column("timestamp_required", Boolean, nullable=False, server_default="true"),
    Column("minimum_evidence_spans", Integer, nullable=False, server_default="1"),
    Column("seller_role_required", Boolean, nullable=False, server_default="true"),
    Column("customer_context_required", Boolean, nullable=False, server_default="false"),
    Column("absence_can_be_evidence", Boolean, nullable=False, server_default="false"),
    Column("human_review_required", Boolean, nullable=False, server_default="false"),
    PrimaryKeyConstraint(
        "rubric_id",
        "rubric_version",
        "criterion_id",
        name="pk_rubric_evidence_requirements",
    ),
    ForeignKeyConstraint(
        ["rubric_id", "rubric_version", "criterion_id"],
        [
            "rubric_criteria.rubric_id",
            "rubric_criteria.rubric_version",
            "rubric_criteria.criterion_id",
        ],
        name="fk_rubric_evidence_requirements_criterion_id_rubric_criteria",
    ),
    CheckConstraint(
        "minimum_evidence_spans >= 0",
        name="ck_rubric_evidence_requirements_min_spans_non_negative",
    ),
)

# ---------------------------------------------------------------------------
# rubric_source_citations
# Enforced FK to knowledge_sections via composite (source_id, section_id).
# ---------------------------------------------------------------------------
rubric_source_citations = Table(
    "rubric_source_citations",
    metadata,
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("citation_order", Integer, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("section_id", Text, nullable=False),
    Column("page_start", Integer, nullable=True),
    Column("page_end", Integer, nullable=True),
    Column("citation_note_code", Text, nullable=True),
    PrimaryKeyConstraint(
        "rubric_id",
        "rubric_version",
        "criterion_id",
        "citation_order",
        name="pk_rubric_source_citations",
    ),
    ForeignKeyConstraint(
        ["rubric_id", "rubric_version", "criterion_id"],
        [
            "rubric_criteria.rubric_id",
            "rubric_criteria.rubric_version",
            "rubric_criteria.criterion_id",
        ],
        name="fk_rubric_source_citations_criterion_id_rubric_criteria",
    ),
    ForeignKeyConstraint(
        ["source_id", "section_id"],
        ["knowledge_sections.source_id", "knowledge_sections.section_id"],
        name="fk_rubric_source_citations_section_knowledge_sections",
    ),
    CheckConstraint(
        "citation_order >= 0", name="ck_rubric_source_citations_order_non_negative"
    ),
    CheckConstraint(
        "page_end IS NULL OR (page_start IS NOT NULL AND page_end >= page_start)",
        name="ck_rubric_source_citations_page_range_valid",
    ),
)

# ---------------------------------------------------------------------------
# transcription_results
# ---------------------------------------------------------------------------
transcription_results = Table(
    "transcription_results",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("full_text", Text, nullable=False),
    Column("detected_language", Text, nullable=True),
    Column("language_confidence", Double, nullable=True),
    Column("processing_duration_seconds", Double, nullable=True),
    Column("provider_confidence", JSON, nullable=False, server_default="[]"),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("call_id", name="pk_transcription_results"),
    ForeignKeyConstraint(
        ["call_id"],
        ["calls.call_id"],
        name="fk_transcription_results_call_id_calls",
    ),
    CheckConstraint(
        "language_confidence IS NULL OR (language_confidence >= 0 AND language_confidence <= 1)",
        name="ck_transcription_results_language_confidence_range",
    ),
    CheckConstraint(
        "processing_duration_seconds IS NULL OR processing_duration_seconds >= 0",
        name="ck_transcription_results_processing_duration_non_negative",
    ),
)

# ---------------------------------------------------------------------------
# transcription_segments
# ---------------------------------------------------------------------------
transcription_segments = Table(
    "transcription_segments",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("segment_order", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("start_seconds", Double, nullable=False),
    Column("end_seconds", Double, nullable=False),
    Column("provider_confidence", JSON, nullable=False, server_default="[]"),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint("call_id", "segment_order", name="pk_transcription_segments"),
    ForeignKeyConstraint(
        ["call_id"],
        ["transcription_results.call_id"],
        name="fk_transcription_segments_call_id_transcription_results",
    ),
    CheckConstraint(
        "segment_order >= 0", name="ck_transcription_segments_order_non_negative"
    ),
    CheckConstraint(
        "end_seconds >= start_seconds",
        name="ck_transcription_segments_end_gte_start",
    ),
)

# ---------------------------------------------------------------------------
# transcription_words
# ---------------------------------------------------------------------------
transcription_words = Table(
    "transcription_words",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("segment_order", Integer, nullable=False),
    Column("word_order", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("start_seconds", Double, nullable=True),
    Column("end_seconds", Double, nullable=True),
    Column("provider_confidence", JSON, nullable=False, server_default="[]"),
    PrimaryKeyConstraint(
        "call_id", "segment_order", "word_order", name="pk_transcription_words"
    ),
    ForeignKeyConstraint(
        ["call_id", "segment_order"],
        ["transcription_segments.call_id", "transcription_segments.segment_order"],
        name="fk_transcription_words_segment_order_transcription_segments",
    ),
    CheckConstraint(
        "word_order >= 0", name="ck_transcription_words_order_non_negative"
    ),
    CheckConstraint(
        "end_seconds IS NULL OR (start_seconds IS NOT NULL AND end_seconds >= start_seconds)",
        name="ck_transcription_words_end_gte_start",
    ),
)

# ---------------------------------------------------------------------------
# diarization_results
# ---------------------------------------------------------------------------
diarization_results = Table(
    "diarization_results",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("processing_duration_seconds", Double, nullable=True),
    Column("provider_confidence", JSON, nullable=False, server_default="[]"),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("call_id", name="pk_diarization_results"),
    ForeignKeyConstraint(
        ["call_id"],
        ["calls.call_id"],
        name="fk_diarization_results_call_id_calls",
    ),
    CheckConstraint(
        "processing_duration_seconds IS NULL OR processing_duration_seconds >= 0",
        name="ck_diarization_results_processing_duration_non_negative",
    ),
)

# ---------------------------------------------------------------------------
# diarization_turns
# ---------------------------------------------------------------------------
diarization_turns = Table(
    "diarization_turns",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("turn_order", Integer, nullable=False),
    Column("speaker_label", Text, nullable=False),
    Column("start_seconds", Double, nullable=False),
    Column("end_seconds", Double, nullable=False),
    Column("provider_confidence", JSON, nullable=False, server_default="[]"),
    PrimaryKeyConstraint("call_id", "turn_order", name="pk_diarization_turns"),
    ForeignKeyConstraint(
        ["call_id"],
        ["diarization_results.call_id"],
        name="fk_diarization_turns_call_id_diarization_results",
    ),
    CheckConstraint("turn_order >= 0", name="ck_diarization_turns_order_non_negative"),
    CheckConstraint(
        "end_seconds > start_seconds", name="ck_diarization_turns_end_gt_start"
    ),
)

# ---------------------------------------------------------------------------
# alignment_results
# ---------------------------------------------------------------------------
alignment_results = Table(
    "alignment_results",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("call_id", name="pk_alignment_results"),
    ForeignKeyConstraint(
        ["call_id"],
        ["calls.call_id"],
        name="fk_alignment_results_call_id_calls",
    ),
)

# ---------------------------------------------------------------------------
# alignment_segments
# ---------------------------------------------------------------------------
alignment_segments = Table(
    "alignment_segments",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("segment_order", Integer, nullable=False),
    Column("source_segment_index", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("start_seconds", Double, nullable=False),
    Column("end_seconds", Double, nullable=False),
    Column("speaker_label", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("alignment_method", Text, nullable=False),
    Column("overlapping_speech", Boolean, nullable=False, server_default="false"),
    Column("candidates", JSON, nullable=False, server_default="[]"),
    PrimaryKeyConstraint("call_id", "segment_order", name="pk_alignment_segments"),
    ForeignKeyConstraint(
        ["call_id"],
        ["alignment_results.call_id"],
        name="fk_alignment_segments_call_id_alignment_results",
    ),
    CheckConstraint(
        "segment_order >= 0", name="ck_alignment_segments_order_non_negative"
    ),
    CheckConstraint(
        "source_segment_index >= 0",
        name="ck_alignment_segments_source_segment_index_non_negative",
    ),
    CheckConstraint(
        "end_seconds >= start_seconds", name="ck_alignment_segments_end_gte_start"
    ),
)

# ---------------------------------------------------------------------------
# alignment_words
# ---------------------------------------------------------------------------
alignment_words = Table(
    "alignment_words",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("segment_order", Integer, nullable=False),
    Column("word_order", Integer, nullable=False),
    Column("source_word_index", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("start_seconds", Double, nullable=True),
    Column("end_seconds", Double, nullable=True),
    Column("speaker_label", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("overlapping_speech", Boolean, nullable=False, server_default="false"),
    Column("candidates", JSON, nullable=False, server_default="[]"),
    PrimaryKeyConstraint(
        "call_id", "segment_order", "word_order", name="pk_alignment_words"
    ),
    ForeignKeyConstraint(
        ["call_id", "segment_order"],
        ["alignment_segments.call_id", "alignment_segments.segment_order"],
        name="fk_alignment_words_segment_order_alignment_segments",
    ),
    CheckConstraint("word_order >= 0", name="ck_alignment_words_order_non_negative"),
    CheckConstraint(
        "source_word_index >= 0",
        name="ck_alignment_words_source_word_index_non_negative",
    ),
    CheckConstraint(
        "end_seconds IS NULL OR (start_seconds IS NOT NULL AND end_seconds >= start_seconds)",
        name="ck_alignment_words_end_gte_start",
    ),
)

# ---------------------------------------------------------------------------
# role_assignment_results
# ---------------------------------------------------------------------------
role_assignment_results = Table(
    "role_assignment_results",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("call_id", name="pk_role_assignment_results"),
    ForeignKeyConstraint(
        ["call_id"],
        ["calls.call_id"],
        name="fk_role_assignment_results_call_id_calls",
    ),
)

# ---------------------------------------------------------------------------
# role_assignments
# ---------------------------------------------------------------------------
role_assignments = Table(
    "role_assignments",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("assignment_order", Integer, nullable=False),
    Column("speaker_label", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("reason_code", Text, nullable=False),
    Column("supporting_evidence_ids", ARRAY(Text), nullable=False, server_default="{}"),
    Column("conflicting_evidence_ids", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint("call_id", "assignment_order", name="pk_role_assignments"),
    ForeignKeyConstraint(
        ["call_id"],
        ["role_assignment_results.call_id"],
        name="fk_role_assignments_call_id_role_assignment_results",
    ),
    CheckConstraint(
        "assignment_order >= 0", name="ck_role_assignments_order_non_negative"
    ),
)

# ---------------------------------------------------------------------------
# call_evaluations
# FK to rubrics enforces the rubric revision exists at evaluation time.
# ---------------------------------------------------------------------------
call_evaluations = Table(
    "call_evaluations",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        name="pk_call_evaluations",
    ),
    ForeignKeyConstraint(
        ["call_id"],
        ["calls.call_id"],
        name="fk_call_evaluations_call_id_calls",
    ),
    ForeignKeyConstraint(
        ["rubric_id", "rubric_version"],
        ["rubrics.rubric_id", "rubrics.version"],
        name="fk_call_evaluations_rubric_id_rubrics",
    ),
)

# ---------------------------------------------------------------------------
# criterion_evaluations
# ---------------------------------------------------------------------------
criterion_evaluations = Table(
    "criterion_evaluations",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("criterion_order", Integer, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("reason_code", Text, nullable=False),
    Column("score", Double, nullable=True),
    Column("score_level_label", Text, nullable=True),
    Column("human_review_required", Boolean, nullable=False, server_default="false"),
    Column("human_review_reason", Text, nullable=True),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "criterion_order",
        name="pk_criterion_evaluations",
    ),
    ForeignKeyConstraint(
        ["call_id", "rubric_id", "rubric_version", "provider_name", "model_name"],
        [
            "call_evaluations.call_id",
            "call_evaluations.rubric_id",
            "call_evaluations.rubric_version",
            "call_evaluations.provider_name",
            "call_evaluations.model_name",
        ],
        name="fk_criterion_evaluations_call_evaluations",
    ),
    UniqueConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "criterion_id",
        name="uq_criterion_evaluations_criterion_id",
    ),
    CheckConstraint(
        "criterion_order >= 0", name="ck_criterion_evaluations_order_non_negative"
    ),
)

# ---------------------------------------------------------------------------
# transcript_evidence_spans
# ---------------------------------------------------------------------------
transcript_evidence_spans = Table(
    "transcript_evidence_spans",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("criterion_order", Integer, nullable=False),
    Column("span_order", Integer, nullable=False),
    Column("source_segment_index", Integer, nullable=False),
    Column("source_word_start_index", Integer, nullable=True),
    Column("source_word_end_index", Integer, nullable=True),
    Column("speaker_label", Text, nullable=False),
    Column("speaker_role", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "criterion_order",
        "span_order",
        name="pk_transcript_evidence_spans",
    ),
    ForeignKeyConstraint(
        [
            "call_id",
            "rubric_id",
            "rubric_version",
            "provider_name",
            "model_name",
            "criterion_order",
        ],
        [
            "criterion_evaluations.call_id",
            "criterion_evaluations.rubric_id",
            "criterion_evaluations.rubric_version",
            "criterion_evaluations.provider_name",
            "criterion_evaluations.model_name",
            "criterion_evaluations.criterion_order",
        ],
        name="fk_transcript_evidence_spans_criterion_evaluations",
    ),
    CheckConstraint("span_order >= 0", name="ck_transcript_evidence_spans_order_non_negative"),
    CheckConstraint(
        "source_segment_index >= 0",
        name="ck_transcript_evidence_spans_source_segment_index_non_negative",
    ),
)

# ---------------------------------------------------------------------------
# absence_evidences  (at most one per criterion evaluation)
# ---------------------------------------------------------------------------
absence_evidences = Table(
    "absence_evidences",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("criterion_order", Integer, nullable=False),
    Column("scope_start_seconds", Double, nullable=False),
    Column("scope_end_seconds", Double, nullable=False),
    Column("speaker_role", Text, nullable=True),
    Column("reason_code", Text, nullable=False),
    Column("reviewed_segment_indexes", ARRAY(Integer), nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "criterion_order",
        name="pk_absence_evidences",
    ),
    ForeignKeyConstraint(
        [
            "call_id",
            "rubric_id",
            "rubric_version",
            "provider_name",
            "model_name",
            "criterion_order",
        ],
        [
            "criterion_evaluations.call_id",
            "criterion_evaluations.rubric_id",
            "criterion_evaluations.rubric_version",
            "criterion_evaluations.provider_name",
            "criterion_evaluations.model_name",
            "criterion_evaluations.criterion_order",
        ],
        name="fk_absence_evidences_criterion_evaluations",
    ),
    CheckConstraint(
        "scope_end_seconds > scope_start_seconds",
        name="ck_absence_evidences_scope_end_gt_start",
    ),
)

# ---------------------------------------------------------------------------
# call_scores
# FK to call_evaluations ensures the evaluation exists.
# ---------------------------------------------------------------------------
call_scores = Table(
    "call_scores",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("aggregation_policy_fingerprint", Text, nullable=False),
    Column("min_scored_weight_coverage", Double, nullable=False),
    Column("min_scored_criterion_coverage", Double, nullable=False),
    Column("require_no_human_review_for_publish", Boolean, nullable=False),
    Column("weighted_performance_score", Double, nullable=True),
    Column("scored_weight_coverage", Double, nullable=True),
    Column("scored_criterion_coverage", Double, nullable=True),
    Column("publication_status", Text, nullable=False),
    Column("quality_flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    Column("created_at", Timestamp(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "aggregation_policy_fingerprint",
        name="pk_call_scores",
    ),
    ForeignKeyConstraint(
        ["call_id"],
        ["calls.call_id"],
        name="fk_call_scores_call_id_calls",
    ),
    ForeignKeyConstraint(
        ["call_id", "rubric_id", "rubric_version", "provider_name", "model_name"],
        [
            "call_evaluations.call_id",
            "call_evaluations.rubric_id",
            "call_evaluations.rubric_version",
            "call_evaluations.provider_name",
            "call_evaluations.model_name",
        ],
        name="fk_call_scores_call_evaluations",
    ),
    CheckConstraint(
        "aggregation_policy_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_call_scores_fingerprint_format",
    ),
    CheckConstraint(
        "weighted_performance_score IS NULL OR "
        "(weighted_performance_score >= 0 AND weighted_performance_score <= 1)",
        name="ck_call_scores_weighted_performance_score_range",
    ),
    CheckConstraint(
        "scored_weight_coverage IS NULL OR "
        "(scored_weight_coverage >= 0 AND scored_weight_coverage <= 1)",
        name="ck_call_scores_scored_weight_coverage_range",
    ),
    CheckConstraint(
        "scored_criterion_coverage IS NULL OR "
        "(scored_criterion_coverage >= 0 AND scored_criterion_coverage <= 1)",
        name="ck_call_scores_scored_criterion_coverage_range",
    ),
    CheckConstraint(
        "min_scored_weight_coverage >= 0 AND min_scored_weight_coverage <= 1",
        name="ck_call_scores_min_weight_coverage_range",
    ),
    CheckConstraint(
        "min_scored_criterion_coverage >= 0 AND min_scored_criterion_coverage <= 1",
        name="ck_call_scores_min_criterion_coverage_range",
    ),
)

# ---------------------------------------------------------------------------
# criterion_score_contributions
# ---------------------------------------------------------------------------
criterion_score_contributions = Table(
    "criterion_score_contributions",
    metadata,
    Column("call_id", Text, nullable=False),
    Column("rubric_id", Text, nullable=False),
    Column("rubric_version", Text, nullable=False),
    Column("provider_name", Text, nullable=False),
    Column("model_name", Text, nullable=False),
    Column("aggregation_policy_fingerprint", Text, nullable=False),
    Column("contribution_order", Integer, nullable=False),
    Column("criterion_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("criterion_weight", Double, nullable=False),
    Column("raw_score", Double, nullable=True),
    Column("normalized_score", Double, nullable=True),
    Column("weighted_points", Double, nullable=True),
    Column("human_review_required", Boolean, nullable=False, server_default="false"),
    Column("human_review_reason", Text, nullable=True),
    Column("reason_code", Text, nullable=False),
    Column("warning_codes", ARRAY(Text), nullable=False, server_default="{}"),
    PrimaryKeyConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "aggregation_policy_fingerprint",
        "contribution_order",
        name="pk_criterion_score_contributions",
    ),
    ForeignKeyConstraint(
        [
            "call_id",
            "rubric_id",
            "rubric_version",
            "provider_name",
            "model_name",
            "aggregation_policy_fingerprint",
        ],
        [
            "call_scores.call_id",
            "call_scores.rubric_id",
            "call_scores.rubric_version",
            "call_scores.provider_name",
            "call_scores.model_name",
            "call_scores.aggregation_policy_fingerprint",
        ],
        name="fk_criterion_score_contributions_call_scores",
    ),
    UniqueConstraint(
        "call_id",
        "rubric_id",
        "rubric_version",
        "provider_name",
        "model_name",
        "aggregation_policy_fingerprint",
        "criterion_id",
        name="uq_criterion_score_contributions_criterion_id",
    ),
    CheckConstraint(
        "contribution_order >= 0",
        name="ck_criterion_score_contributions_order_non_negative",
    ),
    CheckConstraint(
        "criterion_weight > 0",
        name="ck_criterion_score_contributions_weight_positive",
    ),
    CheckConstraint(
        "normalized_score IS NULL OR (normalized_score >= 0 AND normalized_score <= 1)",
        name="ck_criterion_score_contributions_normalized_score_range",
    ),
)

# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
from sqlalchemy import Index  # noqa: E402

Index(
    "ix_rubrics_status_version",
    rubrics.c.rubric_id,
    rubrics.c.status,
    rubrics.c.version_major,
    rubrics.c.version_minor,
    rubrics.c.version_patch,
)
