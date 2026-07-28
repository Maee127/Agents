# Decision Log

Append-only log of notable technical decisions. Newest entries last.

## 2026-07-26: Initial scaffold decisions

- **src layout with hatchling build backend.** Standard, tool-agnostic; installable
  with `pip install -e ".[dev]"` or uv. No Poetry/PDM lock-in.
- **Minimal initial dependencies.** ML/audio libraries (Whisper, pyannote, PyTorch),
  LLM SDKs, Alembic, Celery, and cloud SDKs are deliberately excluded until the
  features that need them are implemented.
- **uvicorn placed in the dev dependency group.** There is no immediate need to run
  the API in production from this package; move it to runtime deps when there is.
- **Settings via pydantic-settings with `APP_` prefix.** `database_url` is a
  `SecretStr` so credentials never appear in repr/str/logs.
- **PostgreSQL 16 with pgvector via `pgvector/pgvector:pg16` image.** Local
  docker-compose defaults work without a `.env` file; a health check is included.
- **Ruff for lint + format, mypy strict, pytest.** Configured in `pyproject.toml`.

## 2026-07-26: Specification alignment pass

- **`audio` is a technical subpackage, not a pipeline stage.** It supports
  ingestion and transcription (normalization, resampling, quality checks); the
  business pipeline remains the specification's six stages. Separating it
  improves testability and provider independence.
- **API serves; workers orchestrate.** The FastAPI layer serves uploads,
  results, review access, and dashboard data. Pipeline execution will be
  handled by queue-triggered workers per the specification. No queue
  dependencies or worker code added yet.
- **`aggregation` planned as its own package.** It will own seller/team
  rollups, trends, averages, and leaderboard calculations, covering the
  specification's Aggregation & dashboard stage; `api` will expose results to
  the future dashboard. No dashboard application code yet.
- **pgvector choice is provisional.** It remains the initial direction, but is
  not final until Phase 2 validates corpus size, retrieval quality, and
  deployment requirements (the specification also lists Pinecone and Weaviate
  as options).

## 2026-07-26: Milestone 1 — domain models

- **Domain models are frozen stdlib dataclasses, not Pydantic.** The domain
  layer must stay free of framework code, and Pydantic would make its
  `ValidationError` part of the domain contract. Invariants are enforced in
  `__post_init__` and raise domain-owned exceptions. No new dependencies.
- **Strict runtime validation without coercion.** Enum fields require real
  enum members (raw strings rejected); durations must be finite, non-negative
  real numbers (booleans rejected); timestamps must be timezone-aware with an
  effective UTC offset; string identifiers are preserved verbatim, never
  stripped or normalized.
- **`CallProcessingStatus` models business-stage completion only.** It records
  which pipeline stage a call has completed (received, validated, transcribed,
  diarized, roles_assigned, evaluated, plus terminal rejected/failed states).
  It is not the worker/orchestration lifecycle: operational states and retry
  states may be modeled separately when queue-based processing is implemented.
- **Exception messages are log-safe.** They contain field names and status
  names only — never PII values or call identifiers.

## 2026-07-26: Local-file ingestion slice

- **ffprobe via a subprocess adapter (`audio/probe.py`).** No Python
  dependencies added; ffprobe must be on PATH (or passed explicitly). Probe
  failures surface as typed domain errors, and error messages never include
  file paths, because filenames can embed phone numbers (PII).
- **`call_id` derived from content.** `call-` plus the first 16 hex characters
  of the file's SHA-256, matching the specification's "generated or derived
  hash" and giving stable identifiers for hash-based duplicate detection.
- **Supported extensions: `.3gp`, `.amr`, `.mp3`, `.wav`.** The first three
  come from the specification's source descriptions; `.wav` is accepted for
  synthetic test audio and future normalized output.
- **Default `call_timestamp` is the file's modification time (UTC)** when the
  caller does not supply one; source-specific parsers will extract real call
  start times later.
- **The ingestion API takes `seller_number`,** matching the canonical
  metadata schema; the `seller_id` question remains open (see below).

## 2026-07-26: Probe error boundary refinement

- **Two operational probe error categories.** `AudioProbeUnavailableError`
  (missing ffprobe executable, timeout, output violating the tool contract —
  the file may be fine) vs `InvalidAudioMediaError` (unreadable media, no
  audio stream, missing or invalid media fields). Ingestion maps only
  `InvalidAudioMediaError` to `CorruptAudioFileError`; environment failures
  propagate unchanged so a misconfigured host cannot mass-mislabel incoming
  files as corrupt. Kept deliberately at two categories.
- **`storage_path` hidden from model reprs.** Local paths end with source
  filenames, which can embed counterparty phone numbers (PII).
- **Single path resolution in ingestion.** The input path is resolved once;
  the same absolute path is used for validation, hashing, probing, and the
  temporary local `storage_path`.

## 2026-07-26: Canonical normalization publication safety

- **Normalization publishes atomically via temp files.** FFmpeg writes to a
  PII-safe temporary file in the destination directory; the temp artifact is
  verified with ffprobe against canonical ASR constraints (WAV, `pcm_s16le`,
  mono, 16 kHz, finite positive duration), hashed, then atomically replaced
  into the deterministic final target.
- **Final artifact naming uses full source SHA-256.** The normalized filename
  is `<full-source-sha256>.asr.wav`, avoiding source filenames/phone numbers
  while remaining deterministic and idempotent.
- **Invalid existing targets are never pre-deleted.** If an existing final
  artifact is invalid, it remains untouched until a fresh replacement is
  successfully generated and verified; regeneration failures leave the prior
  target in place.

## 2026-07-26: Transcription boundary contract

- **Provider-independent transcription models and protocol.** The boundary
  accepts a normalized-audio request contract and returns validated transcript
  models only; provider SDK response objects never escape adapters.
- **Confidence is not forced into a universal score.** Language confidence is
  represented separately from provider-native confidence metrics; metric scales
  are a closed enum (`ZERO_TO_ONE`, `PERCENTAGE`, `LOG_PROBABILITY`,
  `UNSPECIFIED`) to avoid ambiguous free-form strings.
- **No-speech is a valid success shape.** `full_text == ""` and `segments == ()`
  are accepted only when `NO_SPEECH_DETECTED` is explicitly set.
- **Warnings are sanitized to application-controlled codes.** Raw provider
  warning messages are not exposed; warning codes must be safe identifiers.

## 2026-07-28: First real ASR adapter — faster-whisper

- **Local `faster-whisper` is the first concrete ASR adapter.** It implements
  `TranscriptionProvider`, maps into existing transcription models, and keeps
  library objects inside the adapter.
- **Optional `[asr]` extra.** `faster-whisper` is not a default/runtime/dev
  dependency; install with `pip install -e ".[asr,dev]"`. The provider module
  remains importable without the extra; missing dependency fails only on model
  load.
- **Default posture is `local_files_only=True`.** Tests never download models.
  The slow real-model integration test requires `RUN_LOCAL_ASR_TESTS=1`, the
  package installed, and a locally available model.
- **No adapter-level inference timeout.** CTranslate2 work is not reliably
  cancellable via threads/futures; timeouts remain a future worker concern.
- **No result-level aggregate confidence.** Segment/word native metrics are
  preserved; unweighted averages are not invented.
- **Conservative no-speech detection.** Empty/whitespace-only segment sets map
  to `NO_SPEECH_DETECTED`; `no_speech_prob` is evidence only and does not
  discard non-empty speech.
- **Language validation is allowlist-based.** Unsupported codes are rejected
  before inference using a frozen Whisper language-code set. English-only
  models (named `*.en` or loaded models that expose `is_multilingual=False`)
  reject non-`en` expected languages instead of silently coercing to English.
- **Privacy-safe model identity.** Named sizes stay readable (`tiny`, `base`,
  …). Local filesystem paths become `local-model-<sha256-12>` derived from the
  normalized path; path fields are hidden from config `repr`/`str`.
- **Offline local directories.** When `local_files_only=True` and
  `model_size_or_path` is a directory, the adapter preflights
  `config.json`, `model.bin`, and `tokenizer.json` before constructing
  `WhisperModel`, so missing tokenizer files cannot trigger Hugging Face
  `from_pretrained` downloads. No in-adapter model downloader is provided.
- **Provider instances are not thread-safe.** Until worker orchestration exists,
  use one provider instance per single-threaded worker, or serialize access.
  Thread locking, process isolation, and hard timeout enforcement are deferred
  to the worker/orchestration milestone.
- **Full-text composition is deterministic concatenation.** Accepted segment
  texts are joined with `"".join(...)` and may glue words if the provider omits
  inter-segment spacing. No artificial spacing correction is applied in v1.

## 2026-07-28: Diarization boundary contract

- **Provider-independent diarization models and protocol.** The boundary accepts
  a normalized-audio request contract and returns validated speaker-turn models
  only; provider SDK objects never escape adapters.
- **Anonymous call-local speaker labels.** Canonical labels match
  ``^SPEAKER_[0-9]{2,}$`` (e.g. ``SPEAKER_00``, ``SPEAKER_100``). No
  seller/customer semantics in diarization; role assignment stays in
  ``speaker_identity``.
- **Speaker count is derived, not stored.** ``DiarizationResult.speaker_count``
  is computed from unique labels in ``turns``; empty turns naturally yield ``0``.
- **Overlap is preserved.** Cross-speaker overlapping turns remain visible;
  ``OVERLAPPING_SPEECH_DETECTED`` is required exactly when cross-speaker overlap
  exists. Same-speaker overlap is allowed structurally for now.
- **Quality flags are adapter-owned.** Providers/fakes compute flags before
  constructing results; domain models validate consistency but do not mutate
  flags. ``SINGLE_SPEAKER_DETECTED`` is required when exactly one speaker is
  present. Valid no-speech success uses ``turns == ()`` with
  ``NO_SPEECH_SEGMENTS``.
- **Speaker-count constraints.** Requests use either ``exact_expected_speakers``
  or ``min``/``max`` hints, never both. Exact count is enforced by
  ``run_diarization()``; min/max are provider hints only in v1.
  ``SPEAKER_COUNT_UNCERTAIN`` is reserved for explicit provider uncertainty,
  not inferred from hints.
- **Diarization-local confidence metrics.** Parallel to transcription; no
  universal diarization score and no hard-coded short-turn threshold in models.
- **Future real adapter direction.** ``pyannote.audio`` diarization-only is the
  likely first real provider (not WhisperX combined ASR/alignment).

## 2026-07-28: Transcript-speaker alignment boundary

- **Deterministic engine, not a provider adapter.** Alignment combines
  provider-independent ``TranscriptionResult`` and ``DiarizationResult`` and
  uses deterministic interval overlap logic. No external model/provider is used
  in this stage.
- **Anonymous labels preserved.** Alignment assigns existing canonical labels
  (``SPEAKER_XX``) only. It never introduces seller/customer semantics; role
  mapping remains the later ``speaker_identity`` stage.
- **Word-level first, segment fallback.** If a segment's words are all timed,
  words are aligned individually. Otherwise the segment interval is aligned as
  a whole. Mixed method results are valid and explicitly flagged.
- **Ambiguity and unassigned content are retained.** Weak or tied timing
  evidence does not force assignment; results preserve ambiguous/unassigned
  status and deterministic candidate evidence.
- **Same-speaker overlap is unioned for scoring.** Overlap is aggregated by
  canonical speaker label and unioned per target interval to avoid
  double-counting duplicate same-speaker time spans.
- **Tolerance is comparison-only.** A small boundary tolerance is applied only
  during overlap comparison, never by mutating source timestamps. Candidate
  overlap remains bounded to transcript duration, so overlap ratios remain in
  ``[0, 1]``.
- **No processing-duration field in alignment results.** Output is semantic
  deterministic data; orchestration/observability timing belongs to a future
  layer.
- **Result flags are engine-derived.** The engine computes quality flags before
  constructing frozen results; models validate consistency and do not mutate
  inferred flags.

## 2026-07-28: Speaker-role assignment boundary (v1)

- **Deterministic engine with speaker-scoped evidence only.** Every
  ``RoleEvidence`` references one canonical aligned speaker label. Call-level
  evidence is intentionally out of scope in v1.
- **Minimal fixed configuration policy.** ``RoleAssignmentConfig`` includes only
  ``expected_seller_count``, ``expected_customer_count``, and
  ``allow_heuristics``. Authoritative precedence is always highest, complement
  role assignment is unsupported, and heuristics are considered only when
  enabled.
- **Evidence strength is derived from evidence type.** Strength is a computed
  property; invalid type-strength combinations are impossible by construction.
  Mapping: operator/human confirmation -> authoritative; voice-id/channel ->
  strong; known seller source -> moderate; opening/turn-pattern/talk-time ->
  weak.
- **Top-strength-only traceability.** Per speaker, the engine chooses the
  highest strength bucket with evidence and makes decisions only from that
  bucket. Supporting/conflicting evidence IDs contain only top-level evidence
  IDs and are sorted deterministically.
- **Conflict semantics are explicit.** Top-level mixed-role evidence returns
  ``UNKNOWN`` + ``CONFLICTED`` with empty supporting IDs and populated
  conflicting IDs. Authoritative conflicts use
  ``AUTHORITATIVE_CONFLICT``; all other top-strength conflicts use
  ``CONFLICTING_TOP_STRENGTH_EVIDENCE``.
- **Unknown handling is explicit and non-guessing.** No evidence yields
  ``NO_EVIDENCE``. Weak-only evidence with heuristics disabled yields
  ``HEURISTICS_DISABLED``. Neither case carries evidence IDs.
- **Result quality flags are engine-derived; model validation is local-fact
  based.** The result model validates only assignment-inferable conditions
  (unknown/conflict/heuristic/partial/speaker-count shape). Engine-derived
  flags that depend on discarded inputs (e.g., no-role-evidence source context,
  expected-count config context) are trusted as provided and not mutated.
- **Privacy posture retained.** Request ``alignment`` is repr-hidden, evidence
  and assignment models carry no transcript text, and error messages stay
  log-safe (field/status oriented only, no PII/path/payload leakage).

## 2026-07-28: Knowledge-source and sales-rubric boundary (v1)

- **Single `knowledge` package owns the boundary.** ``knowledge.models`` defines
  immutable source/rubric contracts; ``knowledge.rubric`` defines deterministic
  assembly. Existing ``rubric`` and ``knowledge_base`` packages remain
  placeholders; no duplicate models are introduced there.
- **Source knowledge and rubric are distinct objects.** ``KnowledgeSource`` and
  ``KnowledgeSection`` represent approved methodology content; ``SalesRubric``
  and ``RubricCriterion`` represent curated evaluation policy.
- **Source lifecycle is explicit via enum status.** ``KnowledgeSourceStatus``
  distinguishes ``DRAFT``, ``APPROVED``, and ``RETIRED``. Approved rubrics may
  cite only currently approved sources at build time; historical rubric objects
  remain valid value objects even if a source is retired later.
- **Criterion provenance is explicit and strict.** ``CriterionOrigin`` enforces
  that ``SOURCE_BACKED`` criteria require citations, while
  ``ORGANIZATION_DEFINED`` criteria must have no citations in v1.
- **No stored source ID list on rubrics.** ``SalesRubric.source_ids`` is a
  computed property derived deterministically from criterion citations.
- **Criterion order is authored order.** Builder preserves
  ``RubricBuildRequest.criteria`` tuple order exactly; criteria are never
  sorted silently.
- **Scoring scales are explicit and validated.** Each criterion carries an
  immutable ``RubricScoringScale`` with strictly increasing score-level order.
  Builder/model code rejects malformed order instead of normalizing it.
- **Evidence policy lives at criterion level.** ``EvidenceRequirement`` defines
  transcript/timestamp/span/role/human-review requirements; no per-score-level
  evidence counters are modeled in v1.
- **Strict semantic validators.** IDs use safe identifier format; content hashes
  are strict lowercase SHA-256; language tags follow a conservative explicit
  policy; rubric versions use strict SemVer core ``MAJOR.MINOR.PATCH`` only.
- **Deterministic assembly only.** Rubric building validates reference
  integrity, provenance, source status for approved rubrics, and citation range
  containment without LLMs, embeddings, parsers, network calls, or persistence.
- **Privacy and proprietary text treatment.** Source titles/headings/text and
  rubric descriptive guidance are repr-hidden; exceptions remain log-safe and do
  not expose proprietary text, paths, transcripts, or payloads.

## 2026-07-28: Evidence-based call-evaluation boundary (v1)

- **Provider-independent contract with validated provider seam.**
  ``evaluation.models`` defines immutable request/result contracts;
  ``evaluation.provider.run_evaluation()`` performs cross-model validation;
  providers must map output into these contracts.
- **Exact rubric coverage is mandatory.** Every rubric criterion appears exactly
  once in evaluation results, in rubric order; missing/extra/duplicate
  criterion outputs are rejected.
- **Scores must match rubric levels exactly.** Scored results require a score
  equal to one allowed criterion scale level and a matching score-level label.
  Unsupported/interpolated scores are rejected.
- **Evidence references stable transcript indices, not duplicated text.**
  ``TranscriptEvidenceSpan`` stores segment index, optional inclusive source
  word index range, speaker label, and speaker role only. Transcript text is
  not duplicated in evaluation outputs.
- **Role consistency is enforced across boundaries.** Evidence span roles must
  match the role-assignment role for each speaker label; unknown/ambiguous
  roles are never reinterpreted as seller/customer.
- **Absence evidence is explicit and structured.** Absence scoring requires
  dedicated ``AbsenceEvidence`` with validated scope and reviewed segments, and
  is allowed only for criteria whose evidence requirement permits it.
- **Status semantics are strict.** Criterion status is one of
  ``SCORED``, ``NOT_APPLICABLE``, or ``INSUFFICIENT_EVIDENCE`` with
  exact score/evidence/reason consistency rules per status.
- **Human review reason is explicit.** Human review uses
  ``human_review_required`` plus a closed ``human_review_reason`` enum;
  warning codes remain operational/sanitized warnings only.
- **Quality flags are derived and consistency-checked.** Flags cover scored
  completeness, partial evaluation, insufficiency, applicability, absence
  usage, unknown-role material participation, human-review presence, and
  provider warnings.
- **No total score in this stage.** Aggregation, normalization, and seller
  performance summaries remain out of scope for this boundary.

## 2026-07-28: Call-level aggregation and scoring boundary (v1)

- **Applied policy is stored in each score result.** ``CallScoreResult`` retains
  frozen ``AggregationConfig`` so publication readiness and limited-coverage
  outcomes are reproducible from the result object alone.
- **Aggregation preserves evaluation intent exactly.** Each
  ``CriterionScoreContribution`` copies ``reason_code``,
  ``human_review_required``, and ``human_review_reason`` directly from
  ``CriterionEvaluation``; aggregation does not reinterpret criterion outcomes.
- **Normalization and weighting are deterministic and unrounded.** For scored
  criteria, ``normalized_score = (raw_score - scale_min) / (scale_max - scale_min)``
  using the first/last validated scale levels; weighted points are
  ``normalized_score * criterion_weight``; accumulations use ``math.fsum``.
- **Coverage semantics distinguish applicable vs non-applicable criteria.**
  Applicable criteria are scored or insufficient only; all-not-applicable
  calls produce ``None`` coverage metrics, while all-insufficient calls produce
  ``0.0`` coverage metrics.
- **Threshold equality passes.** Limited-coverage flags use strict
  ``coverage < minimum`` checks; equality to configured minima is publishable
  from a coverage standpoint.
- **Publication status has explicit precedence with concurrent flags retained.**
  Precedence is: ``NO_SCORABLE_CRITERIA`` -> ``HUMAN_REVIEW_REQUIRED`` (when
  blocking enabled) -> ``LIMITED_COVERAGE`` -> ``PUBLISHABLE``. Quality flags
  retain concurrent conditions regardless of status precedence.
- **Fully-scored semantics are applicable-rubric scoped.**
  ``FULLY_SCORED_APPLICABLE_RUBRIC`` requires at least one applicable
  criterion, no insufficient criteria, and all applicable criteria scored;
  ``NOT_APPLICABLE`` criteria do not block this flag.
- **Rubric order is preserved end-to-end.** Aggregation requires exact rubric
  criterion coverage and preserves rubric tuple order in contributions with no
  sorting or dictionary-order dependence.
- **Privacy-safe boundary is maintained.** Aggregation request hides rubric and
  evaluation in repr; contributions and result exclude transcript text,
  citations, criterion prose, and proprietary content; exception messages stay
  log-safe and field-oriented.

## Open decisions

- **`seller_number` vs `seller_id`.** The specification's canonical metadata
  schema uses `seller_number` (section 3) while the Stage 7 data model uses
  `seller_id` (section 8). Proposed direction: internal `seller_id` as the
  stable primary key, with `seller_number` retained as an external/source
  attribute when available. Final decision requires customer confirmation; the
  specification will then be amended explicitly, not silently.
