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

## Open decisions

- **`seller_number` vs `seller_id`.** The specification's canonical metadata
  schema uses `seller_number` (section 3) while the Stage 7 data model uses
  `seller_id` (section 8). Proposed direction: internal `seller_id` as the
  stable primary key, with `seller_number` retained as an external/source
  attribute when available. Final decision requires customer confirmation; the
  specification will then be amended explicitly, not silently.
