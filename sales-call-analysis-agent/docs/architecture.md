# Architecture (Initial Scaffold)

> **Status: subordinate document.** `docs/project-specification.md` is the single
> source of truth for this project. If anything in this file conflicts with the
> specification, the specification wins and this file must be updated to match.

## Layout

The project uses a `src` layout with one package, `sales_call_agent`, split into
subpackages that mirror the processing pipeline:

```text
ingestion -> audio -> transcription -> diarization -> speaker_identity -> evaluation
                                                          (rubric)  (knowledge_base)
```

| Package            | Responsibility                                                      |
| ------------------ | ------------------------------------------------------------------- |
| `domain`           | Core models and business rules; no I/O or framework dependencies    |
| `ingestion`        | Accepting and validating incoming call recordings and metadata      |
| `audio`            | Audio preprocessing: normalization, resampling, quality checks      |
| `transcription`    | Speech-to-text transcription                                        |
| `diarization`      | Segmenting audio by who spoke when                                  |
| `speaker_identity` | Mapping diarized segments to participants (agent vs. customer)      |
| `knowledge_base`   | Vector retrieval (PostgreSQL + pgvector) supporting evaluation      |
| `rubric`           | Evaluation criteria, scales, and scoring guidance                   |
| `evaluation`       | Scoring transcripts against the rubric                              |
| `persistence`      | SQLAlchemy persistence layer                                        |
| `api`              | FastAPI application layer (no endpoints yet)                        |

## Layering rules

- `domain` depends on nothing else in the package.
- Pipeline packages may depend on `domain`, never on `api`.
- `api` orchestrates; it must not contain business logic.
- Database access goes through `persistence`; other packages do not open
  connections directly.

## Current state

Scaffold only. No business logic, endpoints, models, or migrations exist yet.
Configuration (`config.py`) and this structure are the only implemented pieces.
