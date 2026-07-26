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

## Open decisions

- **`seller_number` vs `seller_id`.** The specification's canonical metadata
  schema uses `seller_number` (section 3) while the Stage 7 data model uses
  `seller_id` (section 8). Proposed direction: internal `seller_id` as the
  stable primary key, with `seller_number` retained as an external/source
  attribute when available. Final decision requires customer confirmation; the
  specification will then be amended explicitly, not silently.
