# Sales Call Analysis Agent

A modular AI system for turning recorded sales conversations into structured,
speaker-aware, and evidence-grounded performance insights.

The pipeline processes calls through ingestion, audio normalization,
transcription, speaker diarization and alignment, speaker-role assignment,
knowledge retrieval, and rubric-based evaluation.

Its goal is to help sales managers review calls more consistently, identify
recurring coaching opportunities, and transform conversations into measurable
performance data without manually listening to every recording.

## Business Value

Sales teams generate large volumes of recorded conversations, but managers cannot manually review every call consistently.

This creates several common problems:

- coaching depends on a small sample of calls;
- recurring sales mistakes can remain hidden;
- evaluation standards may differ between managers;
- important evidence is difficult to compare across a team;
- call recordings remain underused as a source of performance data.

The Sales Call Analysis Agent is designed to turn those recordings into structured, speaker-aware, and reviewable information.

Its intended value is to help organizations:

- review more calls without requiring managers to listen to every recording;
- identify recurring coaching opportunities;
- evaluate calls against consistent sales rubrics;
- preserve transcript evidence behind scores and feedback;
- compare performance across calls and, eventually, across teams;
- convert conversational data into measurable management insights.

The objective is not to replace sales managers or coaches, but to give them a more consistent and evidence-grounded way to inspect call quality.

## Project Status

**Status: Active engineering build**

The core foundations for the Sales Call Analysis Agent are already implemented, including:

- local audio ingestion and validation
- canonical audio normalization with FFmpeg
- provider-independent transcription interfaces
- hardened `faster-whisper` integration
- provider-independent diarization interfaces
- deterministic transcript-speaker alignment
- privacy-aware domain models and exception handling
- persistence foundations with PostgreSQL, SQLAlchemy, Alembic, and pgvector
- orchestration foundations and automated tests

### Current Development

Development is progressing incrementally across the remaining application layers, including:

- speaker-role assignment (`SELLER`, `CUSTOMER`, `UNKNOWN`)
- persistence and unit-of-work integration
- pipeline orchestration
- API integration
- knowledge-base and rubric evaluation
- call-level and team-level reporting


### Remaining Product Roadmap

- complete persistent storage across the processing pipeline
- complete orchestration and background execution
- upload and result APIs
- knowledge-base ingestion
- configurable sales rubrics
- retrieval-augmented evaluation
- evidence-grounded scoring
- call-level and team-level reporting
- management dashboard
- observability, security, and production hardening


> See `docs/project-specification.md` for the project source of truth and
> `docs/architecture.md`.

## Current Limitations

The project is still an active engineering build and should not yet be interpreted as a production-ready sales analytics platform.

Current limitations include:

- speaker-role assignment is still under active development;
- rubric-based evaluation is not yet complete;
- management reporting and dashboard layers are still planned;
- production authentication and authorization are not implemented;
- large-scale evaluation across diverse call types has not yet been completed;
- production-grade monitoring, deployment, and operational controls are still future work;
- real-world use requires appropriate consent, privacy controls, and organization-specific retention policies.

The current focus is on building and validating the processing foundation before expanding into higher-level evaluation and reporting.

## Requirements

- Python 3.12+
- Docker (only for the local PostgreSQL/pgvector database)

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

Optional local ASR (faster-whisper):

```bash
pip install -e ".[asr,dev]"
```

The ASR extra is not required for domain, ingestion, normalization, or most
tests. The provider module imports without it; model loading fails clearly if
the extra is missing.

Default ASR posture is offline (`local_files_only=True`). Named model sizes
(e.g. `tiny`) load from the local Hugging Face cache only. If you point
`model_size_or_path` at a local CTranslate2 model directory, that directory
must already contain at least:

- `config.json`
- `model.bin`
- `tokenizer.json`

Missing `tokenizer.json` is rejected before model construction so faster-whisper
cannot fall back to downloading a tokenizer from Hugging Face. This project
does not ship a model downloader; obtain or convert models out of band.

Configuration is environment-driven with safe local defaults, so no `.env`
file is required for a first run. To customize, copy `.env.example` to `.env`
and edit it. Never commit `.env`.

## Local database

```bash
docker compose up -d
```

Starts PostgreSQL 16 with the pgvector extension available, plus a health
check. Default credentials are local-only throwaways (`postgres`/`postgres`,
database `sales_calls`); override them via `.env` if desired.

## Development commands

| Command                | Purpose                       |
| ---------------------- | ----------------------------- |
| `pytest`               | Run the fast test suite       |
| `ruff check .`         | Lint                          |
| `ruff format --check .`| Verify formatting             |
| `mypy src`             | Static type checking (strict) |

Local ASR integration tests are opt-in and skipped by default:

```bash
# Requires: [asr] installed, tiny model already cached locally, no network
set RUN_LOCAL_ASR_TESTS=1
pytest -m slow
```

## Project layout

```text
src/sales_call_agent/   application package (pipeline subpackages)
tests/                  unit and integration tests, fixtures
scripts/                developer entry points (run_sample_call.py)
docs/                   specification, architecture, decision log
```
