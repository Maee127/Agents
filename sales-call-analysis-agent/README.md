# Sales Call Analysis Agent

Agent that analyzes recorded sales calls end to end: ingestion, audio
preprocessing, transcription, speaker diarization, speaker identification, and
rubric-based evaluation backed by a PostgreSQL + pgvector knowledge base.

> **Status: scaffold only.** The repository structure, configuration, and
> tooling are in place; no business logic is implemented yet.
> See `docs/project-specification.md` (source of truth) and
> `docs/architecture.md`.

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
