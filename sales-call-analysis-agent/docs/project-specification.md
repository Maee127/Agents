# Sales call analysis agent

**Technical project specification**

Speech-to-text transcription, speaker role assignment, and rubric-based sales performance scoring using a RAG-grounded evaluation engine.

> **Status:** Authoritative project specification.
> This document is the source of truth for the initial system design.
> If another project document conflicts with this specification, this document takes precedence unless a later architecture decision explicitly records an approved change.

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [System architecture overview](#2-system-architecture-overview)
3. [Stage 1 — Audio ingestion](#3-stage-1--audio-ingestion)
   - [Canonical metadata schema](#canonical-metadata-schema)
   - [Validation before processing](#validation-before-processing)
   - [Storage and triggering](#storage-and-triggering)
4. [Stage 2 & 3 — Transcription, diarization, and role assignment](#4-stage-2--3--transcription-diarization-and-role-assignment)
   - [Assigning seller vs. customer roles](#assigning-seller-vs-customer-roles)
   - [Known limitations to plan for](#known-limitations-to-plan-for)
5. [Stage 4 — Knowledge base from the sales books](#5-stage-4--knowledge-base-from-the-sales-books)
6. [Stage 5 — Rubric design](#6-stage-5--rubric-design)
   - [Example behavioral anchor](#example-behavioral-anchor)
7. [Stage 6 — Evaluation engine](#7-stage-6--evaluation-engine)
   - [Consistency measures](#consistency-measures)
8. [Stage 7 — Aggregation & dashboard](#8-stage-7--aggregation--dashboard)
   - [Data model](#data-model)
   - [Dashboard views](#dashboard-views)
9. [Recommended technology stack](#9-recommended-technology-stack)
10. [Risks and open questions](#10-risks-and-open-questions)
11. [Suggested phased approach](#11-suggested-phased-approach)

## 1. Executive summary

The customer records daily sales calls per seller, mostly captured through consumer call-recording apps and PBX/CDR software rather than a dedicated call-center platform. They want each call transcribed and evaluated for sales quality against the practices described in a set of sales methodology books they provide, with results tracked per seller over time.

This is a speech analytics and RAG-based coaching evaluation pipeline: audio is ingested, transcribed, and speaker-separated; the sales books are distilled into a scoreable rubric and indexed as a retrieval knowledge base; an LLM evaluation engine scores each call against that rubric with citations back to the transcript; and results roll up into a per-seller dashboard.

## 2. System architecture overview

The pipeline has six stages. Each is described in detail in the sections that follow.

| Stage | Purpose |
| --- | --- |
| 1. Ingestion | Receive daily audio batches per seller, parse source-specific filenames/logs into a canonical metadata record. |
| 2. Transcription | Convert audio to text with word-level timestamps (ASR). |
| 3. Diarization & role assignment | Separate speaker turns and determine which speaker is the seller vs. the customer. |
| 4. Knowledge base | Distill the sales books into a rubric and index supporting excerpts for retrieval (RAG). |
| 5. Evaluation engine | Score each call per rubric dimension using an LLM, grounded in retrieved book excerpts, with citations. |
| 6. Aggregation & dashboard | Roll up scores per seller over time; present trends, leaderboards, and call drill-down. |

## 3. Stage 1 — Audio ingestion

Files arrive as one daily batch per seller. Two source types have been identified so far:

- Consumer call-recorder apps (e.g. “Automatic Call Recorder by Call Team”) — typically mono audio (.3gp/.amr/.mp3), with the counterparty phone number often embedded in the filename.
- CDR / PBX software exports — typically filename or log-based records (e.g. Asterisk-style naming), sometimes with an accompanying CSV/log file.

Because these sources have no shared metadata format, ingestion requires a source-specific parser per app/system that normalizes filenames and any accompanying logs into one canonical schema, rather than a single generic import step.

### Canonical metadata schema

| Field | Description |
| --- | --- |
| `call_id` | Unique identifier for the call (generated or derived hash). |
| `seller_number` | Identifies the sales rep; source of truth for per-rep rollups. |
| `source_type` | `recorder_app` or `cdr_software` — determines which parser produced the record. |
| `call_timestamp` | Call start time, ISO 8601. |
| `duration_seconds` | Call length. |
| `counterparty_phone` | Extracted where available; usable as a pseudo customer identifier. |
| `original_filename` | Retained for traceability back to the source file. |
| `audio_channels` | `mono` or `stereo` — determines whether diarization is required. |
| `storage_path` | Location of the stored audio file. |

### Validation before processing

- File integrity — reject corrupt or incomplete uploads.
- Format normalization — standardize sample rate/channel count for the ASR step.
- Silence/duration checks — filter out empty calls, voicemails, and no-answer recordings.
- Duplicate detection — hash-based check so a call is not double-counted.

### Storage and triggering

Object storage (S3-equivalent), organized by seller and date, encrypted at rest with role-based access controls given the presence of PII (phone numbers, recorded conversations). New files trigger a queue message (SQS/Pub-Sub or equivalent) that starts the transcription worker, decoupling ingestion from processing so failures don't lose files.

## 4. Stage 2 & 3 — Transcription, diarization, and role assignment

Because most recordings are mono (both speakers mixed into a single track), channel-based speaker separation is not available. The pipeline instead uses a three-step process:

- Transcription with word-level timestamps (e.g. Whisper).
- Speaker diarization to segment the audio into speaker turns (e.g. pyannote-audio), producing generic “Speaker A / Speaker B” labels.
- Alignment of transcript words to diarization segments by timestamp (e.g. via WhisperX), producing a speaker-labeled transcript.

### Assigning seller vs. customer roles

Diarization alone does not identify which speaker is the seller. Since files are batched daily per seller, voice embeddings can be clustered across that day's calls: the voice that recurs across nearly all calls is the seller, while the other voice changes call to call (the customer). A more robust production alternative is a short one-time voice enrollment sample per seller, compared directly against each call rather than relying on cross-call consistency.

### Known limitations to plan for

- Mono, compressed phone audio produces higher diarization error rates than studio-quality dual-channel recordings.
- Overlapping speech, hold music, and voicemail calls need explicit handling rather than being scored as normal conversations.
- Recording consent/compliance is a legal question for the customer to confirm with counsel given personal-phone-sourced audio.

## 5. Stage 4 — Knowledge base from the sales books

The sales methodology books are chunked, embedded, and stored in a vector database, forming the retrieval-augmented generation (RAG) layer used to ground the evaluation engine's scoring in the customer's own training material rather than generic notions of “good sales.”

Before building this, it's worth confirming with the customer which methodology the books represent (e.g. SPIN Selling, Challenger Sale, Sandler) — different frameworks can disagree on tactics, and the rubric should reflect what the customer actually wants reps trained on.

## 6. Stage 5 — Rubric design

The books are distilled into a fixed, structured rubric rather than relying on open-ended retrieval alone, which improves scoring consistency and explainability. The process:

- Identify the core sales framework the books teach.
- Extract evaluation dimensions (e.g. opening, needs discovery, objection handling, active listening, closing, tone/compliance).
- Define behavioral anchors for each score level — concrete, observable descriptions rather than vague adjectives.
- Validate the draft rubric with the customer's sales manager to confirm it matches their actual process.
- Pilot on a sample of calls and calibrate against human scoring before trusting it at scale.

### Example behavioral anchor

| Score | Needs discovery — example anchor |
| --- | --- |
| 5 | Asked multiple open-ended questions before pitching; later referenced the customer's specific situation. |
| 3 | Asked a couple of surface-level questions but moved to pitching quickly. |
| 1 | Pitched immediately with no discovery questions. |

## 7. Stage 6 — Evaluation engine

For each call, and for each rubric dimension, the evaluation engine:

- Retrieves the book excerpts most relevant to that dimension from the knowledge base.
- Passes the role-labeled transcript, the dimension's rubric description, and the retrieved excerpts to an LLM.
- Requires a structured (JSON) response: a score, a written justification, and a transcript timestamp/quote reference — so every score is traceable to a specific moment in the call.

Scoring each dimension in a separate call (rather than one prompt scoring everything at once) tends to produce more focused, defensible justifications, at the cost of more calls per conversation — worth validating empirically.

### Consistency measures

- Low or zero sampling temperature to reduce run-to-run variance.
- Multiple scoring passes per dimension with averaging or majority vote, especially for borderline scores.
- A pinned model version so scoring behavior doesn't silently drift.
- Periodic calibration against human-reviewed calls to confirm the rubric and prompts are producing scores managers agree with.

## 8. Stage 7 — Aggregation & dashboard

### Data model

- `calls` — `call_id`, `seller_id`, `date`, `duration`, `source`
- `call_scores` — `call_id`, `dimension`, `score`, `justification`, `transcript_reference` (one row per dimension per call)
- `sellers` — rep metadata

This supports straightforward rollups: average score per dimension per seller per week, trend over time, team-wide comparisons, and — if outcome data (won/lost) becomes available — correlation between specific scoring dimensions and actual results.

### Dashboard views

- Team overview — team averages and the weakest common dimension across the group, often the clearest signal for a training intervention.
- Rep scorecard — one seller's trend over time, broken down by dimension.
- Call drill-down — the transcript excerpt and justification behind any individual score, so results are never a black box.

Given the drill-down-to-transcript requirement, a purpose-built web app is likely worth the extra build effort over a generic BI tool, though a BI tool (e.g. pointed at the scoring database) is a faster way to validate the concept early on.

## 9. Recommended technology stack

| Component | Suggested tooling |
| --- | --- |
| Transcription (ASR) | Whisper (self-hosted) or a managed ASR API |
| Diarization | pyannote-audio; WhisperX for combined transcription + alignment |
| Voice embeddings | speechbrain or pyannote embedding models, for role assignment |
| Vector database | e.g. pgvector, Pinecone, or Weaviate for the book knowledge base |
| Evaluation LLM | Claude or another current-generation LLM, called per rubric dimension |
| Storage | S3-compatible object storage for audio; Postgres for structured records |
| Orchestration | Queue-based workers (SQS/Pub-Sub) triggered on file arrival |
| Dashboard | Custom web app, or a BI tool (Metabase/Looker) for an early version |

## 10. Risks and open questions

- Recording consent/compliance for personal-phone-sourced calls — needs confirmation from the customer's legal counsel.
- Diarization accuracy on mono, compressed phone audio — should be validated on real sample files early.
- LLM scoring consistency — requires a tightly specified rubric and calibration against human reviewers before the customer relies on it.
- Exact daily batch structure (folder-per-seller vs. filename-encoded seller ID) — needs confirmation to finalize the ingestion parser.
- Whether calls occur in multiple languages, which would affect ASR and evaluation model choice.
- Cost per call (ASR + diarization + multiple LLM scoring calls) — worth estimating once call volume is known.

## 11. Suggested phased approach

- Phase 1 — Ingestion and transcription pipeline on a sample of real files from both sources; validate diarization quality.
- Phase 2 — Rubric design and knowledge base, validated with the customer's sales manager on a small set of calls.
- Phase 3 — Evaluation engine with structured scoring, calibrated against human-reviewed calls.
- Phase 4 — Aggregation, dashboard, and rollout to full daily volume.
