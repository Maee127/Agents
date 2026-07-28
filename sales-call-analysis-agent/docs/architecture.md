# Architecture (Initial Scaffold)

> **Status: subordinate document.** `docs/project-specification.md` is the single
> source of truth for this project. If anything in this file conflicts with the
> specification, the specification wins and this file must be updated to match.

## Layout

The project uses a `src` layout with one package, `sales_call_agent`. Subpackages
mirror the specification's business pipeline, with supporting technical packages
around it:

```text
ingestion -> transcription -> diarization -> alignment -> speaker_identity -> knowledge -> evaluation -> aggregation
```

- `audio` is a technical subpackage supporting ingestion and transcription; it is
  not an additional business pipeline stage.
- `knowledge` currently owns source-knowledge and rubric value contracts plus deterministic rubric assembly.
- `aggregation` now owns deterministic call-level score aggregation from criterion evaluations.
- `rubric` and `knowledge_base` remain placeholders for future split/expansion only.
- `domain`, `persistence`, and `api` are cross-cutting layers.

| Package                 | Responsibility                                                        |
| ----------------------- | --------------------------------------------------------------------- |
| `domain`                | Core models and business rules; no I/O or framework dependencies      |
| `ingestion`             | Accepting and validating incoming call recordings and metadata        |
| `audio`                 | Technical audio preprocessing (normalization, resampling, quality checks) supporting ingestion and transcription |
| `transcription`         | Speech-to-text transcription                                           |
| `diarization`           | Segmenting audio by who spoke when                                     |
| `alignment`             | Deterministic timestamp alignment of transcript content to anonymous speaker labels |
| `speaker_identity`      | Deterministic mapping from anonymous aligned speakers to `SELLER`/`CUSTOMER`/`UNKNOWN` with evidence traceability |
| `knowledge`             | Provider-independent knowledge-source and rubric contracts plus deterministic rubric assembly |
| `knowledge_base`        | Vector retrieval (PostgreSQL + pgvector) supporting evaluation         |
| `rubric`                | Evaluation criteria, scales, and scoring guidance                      |
| `evaluation`            | Provider-independent criterion-level call evaluation contracts, validation boundary, and provider seam |
| `aggregation`           | Deterministic call-level score aggregation, coverage metrics, and publication readiness derivation |
| `persistence`           | SQLAlchemy persistence layer                                           |
| `api`                   | FastAPI layer serving uploads, results, review access, and dashboard data (no endpoints yet) |

## Layering rules

- `domain` depends on nothing else in the package.
- Pipeline packages may depend on `domain`, never on `api`.
- `api` serves uploads, results, review access, and data for the future dashboard.
  It does not orchestrate the pipeline and must not contain business logic.
- Pipeline execution will be handled by queue-triggered workers, per the
  specification. No queue dependencies or worker code exist yet.
- Database access goes through `persistence`; other packages do not open
  connections directly.

## Planned infrastructure

Planned architecture only — no dependencies or implementation files exist yet:

- Object storage adapter for audio assets (S3-equivalent), organized by seller and
  date, encrypted at rest with role-based access.
- Queue abstraction and worker entry points that start pipeline processing when
  new files arrive.
- PostgreSQL for structured records (calls, scores, sellers).
- pgvector for knowledge-base embeddings (provisional until Phase 2 validates
  corpus size, retrieval quality, and deployment requirements).

## Current state

Scaffold only. No business logic, endpoints, workers, database models, migrations,
or dashboard code exist yet. Configuration (`config.py`) and this structure are
the only implemented pieces.
