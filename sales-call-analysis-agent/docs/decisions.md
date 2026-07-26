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
