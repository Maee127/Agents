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
| `pytest`               | Run the test suite            |
| `ruff check .`         | Lint                          |
| `ruff format --check .`| Verify formatting             |
| `mypy src`             | Static type checking (strict) |

## Project layout

```text
src/sales_call_agent/   application package (pipeline subpackages)
tests/                  unit and integration tests, fixtures
scripts/                developer entry points (run_sample_call.py)
docs/                   specification, architecture, decision log
```
