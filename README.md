# Applied AI Agents Portfolio

A portfolio of practical AI systems designed to transform complex, unstructured business data into structured, reviewable, and actionable outputs.

This repository contains three independent applied AI projects:

1. **Catalog Vision Extractor** — converts visually inconsistent PDF product catalogues into normalized Excel datasets.
2. **Contract Agent** — analyzes contracts clause by clause and produces structured, evidence-aware risk findings through a FastAPI application.
3. **Sales Call Analysis Agent** — transforms recorded sales conversations into speaker-aware transcripts, evaluation evidence, and progressively richer performance insights.

These projects focus on the engineering required around AI models—not only the model call itself.

Across the repository, that includes ingestion, preprocessing, provider abstraction, structured outputs, validation, caching, failure isolation, persistence, testing, APIs, privacy-aware handling, and human review.

![Applied AI Agents Portfolio Overview](docs/images/agents_portfolio_overview.png)

---

## Projects at a Glance

| Project | Business Problem | Core Approach | Interface | Current Stage |
|---|---|---|---|---|
| [Catalog Vision Extractor](./catalog-vision-extractor/) | Product and price data is trapped inside long, visually complex PDF catalogues. | Vision-LLM page classification and structured extraction followed by deterministic normalization. | Python CLI and Excel output | Functional, tested portfolio pipeline |
| [Contract Agent](./contract-agent/) | Important obligations and risks are difficult to identify quickly in long agreements. | Clause-aware document processing and structured local-LLM analysis with source-evidence checks. | FastAPI API and browser UI | Working local MVP |
| [Sales Call Analysis Agent](./sales-call-analysis-agent/) | Managers cannot manually review every sales call consistently or convert conversations into measurable coaching insights. | Provider-independent audio processing, transcription, diarization, alignment, role assignment, and rubric-based evaluation. | Python package; API and dashboard planned | Active engineering build |

---

# 1. Catalog Vision Extractor

Commercial catalogues often combine cover pages, marketing content, product descriptions, technical drawings, specifications, and price tables.

Their layouts differ across brands, making fixed-coordinate and text-only extraction methods fragile.

The Catalog Vision Extractor renders each PDF page as an image, identifies pages containing price tables, extracts visible product rows into structured data, validates and normalizes the results, and merges them into a consistent Excel workbook.

![Catalog Vision Extractor Architecture](docs/images/catalog_vision_extractor_architecture.png)

## Engineering Highlights

- Page-level PDF processing with PyMuPDF
- Vision-based page classification
- Anthropic and OpenAI provider abstraction
- Structured model outputs validated with Pydantic
- Concurrent page classification and extraction
- Cache keys based on page content, prompt, and model
- Automatic cache invalidation after prompt or model changes
- Retry handling for transient API failures
- Detection of truncated model responses
- Per-page failure isolation
- Low-confidence review flags
- Deterministic normalization
- Duplicate and malformed-row handling
- Idempotent replacement by brand and price-list version
- Atomic Excel writes
- API-free unit tests
- GitHub Actions continuous integration

## Run It

```bash
cd catalog-vision-extractor

python -m venv .venv
source .venv/bin/activate

# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
```

Configure an Anthropic or OpenAI API key in your local environment, then process one catalogue:

```bash
python -m src.pipeline \
  --pdf data/input/acme_2026.pdf \
  --brand ACME \
  --version 2026
```

Process every PDF in the configured input directory:

```bash
python -m src.pipeline --all --version 2026
```

Force reprocessing without cached results:

```bash
python -m src.pipeline \
  --pdf data/input/acme_2026.pdf \
  --brand ACME \
  --version 2026 \
  --no-cache
```

The consolidated workbook is written to:

```text
catalog-vision-extractor/data/output/master_pricelist.xlsx
```

See the [project README](./catalog-vision-extractor/README.md) and [output schema](./catalog-vision-extractor/docs/schema.md) for detailed configuration, behavior, and limitations.

---

# 2. Contract Agent

Contract Agent is a local-first MVP for clause-level contract review.

It extracts text from PDF or TXT agreements, identifies clause boundaries, analyzes each clause with a locally stored language model, validates the structured response against source evidence, and exposes the findings through a lightweight API and browser interface.

The system is intended to help users locate important obligations, unusual terms, and potentially risky clauses more efficiently.

It is a **decision-support tool, not a replacement for professional legal review**.

![Contract Agent Architecture](docs/images/contract_agent_architecture.png)

## Engineering Highlights

- PDF and TXT ingestion
- Detection of empty or unsupported documents
- Scanned-document handling
- Structural clause splitting
- Sentence-boundary fallback
- Local Qwen2.5-7B inference through Transformers
- Structured clause verdicts
- Clause type, summary, obligations, and risk-level outputs
- Source-quote verification
- Rejection of unsupported risk evidence
- Per-clause failure isolation
- Progress callbacks
- In-memory background job queue
- Single-worker local-model processing
- Upload type and size validation
- FastAPI endpoints
- Lightweight responsive browser UI
- Unit and integration test organization

## Run It

The project targets Python 3.13 and expects access to a compatible local model.

```bash
cd contract-agent

python -m venv .venv
source .venv/bin/activate

# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
```

Place the local model in the expected project directory or configure its path through the environment.

Start the application:

```bash
uvicorn app.main:app --reload
```

Open the local interface at:

```text
http://127.0.0.1:8000
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

Run the tests:

```bash
pytest
```

See the [Contract Agent README](./contract-agent/README.md) for project-specific setup and implementation notes.

> **Responsible-use notice:** Contract Agent provides automated analysis for educational and decision-support purposes. Its output may be incomplete or incorrect and should be reviewed by a qualified legal professional before legal or business decisions are made.

---

# 3. Sales Call Analysis Agent

The Sales Call Analysis Agent is a modular AI system for turning recorded sales conversations into structured, speaker-aware, and evidence-grounded performance insights.

The pipeline processes calls through audio ingestion and validation, canonical normalization, transcription, speaker diarization, transcript-speaker alignment, speaker-role assignment, and progressively richer sales-performance evaluation.

Its goal is to help sales managers review calls more consistently, identify recurring coaching opportunities, and transform conversations into measurable performance data without manually listening to every recording.

![Sales Call Analysis Agent Architecture](docs/images/sales_call_analysis_agent_architecture.png)

## Implemented Foundations

The current implementation includes completed or substantially implemented foundations for:

- domain models for calls, audio assets, metadata, and processing states
- validated processing-state transitions
- local-file ingestion
- file hashing and size validation
- audio probing through `ffprobe`
- privacy-aware exception handling and object representations
- canonical ASR audio normalization through `ffmpeg`
- deterministic normalized-file naming
- post-conversion audio validation
- provider-independent transcription contracts
- hardened `faster-whisper` adapter
- offline-first local ASR configuration
- provider-independent diarization contracts
- deterministic transcript-speaker alignment
- PostgreSQL 16 and pgvector development environment
- SQLAlchemy and Alembic persistence foundations
- orchestration foundations
- environment-based configuration
- strict static typing
- automated linting, formatting, and tests
- architecture, specification, and decision documentation

## Current Development Path

Development is progressing incrementally across the remaining application layers.

### Implemented Foundations

1. Domain model and processing-state rules
2. Audio ingestion and probing
3. Canonical audio normalization
4. Provider-independent transcription
5. Hardened local `faster-whisper` integration
6. Provider-independent speaker diarization
7. Deterministic transcript-speaker alignment
8. Persistence foundations
9. Orchestration foundations

### Active Development

- speaker-role assignment:
  - `SELLER`
  - `CUSTOMER`
  - `UNKNOWN`
- persistence and unit-of-work integration
- pipeline orchestration

### Remaining Product Roadmap

- complete API integration
- knowledge-base ingestion
- sales methodology and rubric representation
- retrieval-augmented evaluation
- evidence-grounded scoring
- human-review workflow
- call-level reports
- team-level aggregation
- management dashboard
- observability, security, and production hardening

## Architecture

```text
sales-call-analysis-agent/
├── .cursor/
│   └── rules/
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   └── project-specification.md
├── migrations/
├── scripts/
├── src/
│   └── sales_call_agent/
│       ├── aggregation/
│       ├── alignment/
│       ├── api/
│       ├── audio/
│       ├── diarization/
│       ├── domain/
│       ├── evaluation/
│       ├── infrastructure/
│       ├── ingestion/
│       ├── knowledge/
│       ├── knowledge_base/
│       ├── orchestration/
│       ├── persistence/
│       ├── rubric/
│       ├── speaker_identity/
│       └── transcription/
├── tests/
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Development Setup

```bash
cd sales-call-analysis-agent

python -m venv .venv
source .venv/bin/activate

# Windows:
# .venv\Scripts\activate

pip install -e ".[dev]"
```

Install the optional local ASR dependencies:

```bash
pip install -e ".[asr,dev]"
```

Start the local PostgreSQL 16 and pgvector service:

```bash
docker compose up -d
```

Run the engineering checks:

```bash
ruff format --check .
ruff check .
mypy src
pytest
```

The local ASR integration tests are opt-in because they require a compatible model to be available locally.

For detailed design decisions and current implementation status, see:

- [Project README](./sales-call-analysis-agent/README.md)
- [Project Specification](./sales-call-analysis-agent/docs/project-specification.md)
- [Architecture](./sales-call-analysis-agent/docs/architecture.md)
- [Decision Log](./sales-call-analysis-agent/docs/decisions.md)

> **Privacy notice:** Sales recordings and transcripts may contain personal, confidential, or commercially sensitive information. Production use requires appropriate consent, access controls, retention policies, encryption, and jurisdiction-specific compliance review.

---

# Shared Engineering Themes

Although each project addresses a different business problem, the repository demonstrates several recurring engineering principles.

## Reliable AI Boundaries

Model responses are treated as untrusted external inputs.

Structured outputs are validated before they enter downstream business logic.

## Provider Independence

Where practical, model-specific implementations are placed behind stable interfaces so the surrounding system does not depend directly on a single provider.

## Deterministic Processing

Normalization, hashing, schemas, cache rules, and explicit state transitions make probabilistic AI components easier to operate and test.

## Failure Isolation

A failed page, clause, audio segment, or provider call should not unnecessarily terminate an entire processing job.

## Human Review

AI outputs are designed to remain inspectable.

Low-confidence results, source evidence, structured findings, and review states support human verification.

## Privacy-Aware Design

File paths, filenames, customer documents, contracts, audio recordings, transcripts, credentials, and model artifacts are treated as potentially sensitive.

## Testable Architecture

Core business logic is separated from external providers and infrastructure to support unit testing without requiring paid APIs, databases, or large local models.

---

# Technology Overview

## Languages and Application Layer

- Python
- FastAPI
- Uvicorn
- HTML
- JavaScript
- Jupyter Notebook

## AI and Machine Learning

- OpenAI APIs
- Anthropic APIs
- Vision-capable language models
- Qwen2.5
- Transformers
- PyTorch
- faster-whisper
- Provider-independent ASR and diarization interfaces

## Document and Audio Processing

- PyMuPDF
- PyPDF
- FFmpeg
- FFprobe

## Data and Persistence

- Pydantic
- pandas
- openpyxl
- JSON
- Excel
- PostgreSQL
- SQLAlchemy
- Alembic
- pgvector

## Engineering Tooling

- pytest
- Ruff
- mypy
- Docker Compose
- GitHub Actions
- Environment-based configuration

---

# Repository Structure

```text
Agents/
├── .github/
│   └── workflows/
├── docs/
│   └── images/
├── catalog-vision-extractor/
│   ├── docs/
│   ├── src/
│   ├── tests/
│   └── README.md
├── contract-agent/
│   ├── app/
│   ├── src/
│   ├── tests/
│   └── README.md
├── sales-call-analysis-agent/
│   ├── docs/
│   ├── migrations/
│   ├── scripts/
│   ├── src/
│   ├── tests/
│   └── README.md
├── .gitignore
└── README.md
```

Each project is self-contained and maintains its own dependencies, documentation, setup instructions, tests, and development status.

---

# Portfolio Focus

This repository documents my work in applied AI engineering, particularly:

- AI agents for business workflows
- multimodal document processing
- Vision-LLM pipelines
- speech and audio intelligence
- local and hosted model integration
- structured extraction from unstructured data
- retrieval-augmented evaluation
- reliable orchestration around probabilistic systems
- business-facing AI prototypes
- human-review and decision-support systems

The central objective is not simply to call an AI model.

It is to build the surrounding system required to make AI output **operational, inspectable, and useful in a real workflow**.

---

# Project Status

These are portfolio-scale and MVP-oriented applied AI systems that continue to evolve.

| Project | Status |
|---|---|
| Catalog Vision Extractor | Functional modular pipeline with classification, extraction, validation, caching, testing, and Excel export |
| Contract Agent | Working local MVP with clause analysis, background processing, FastAPI endpoints, and a browser interface |
| Sales Call Analysis Agent | Active multi-stage engineering build with audio, transcription, diarization, alignment, persistence, and orchestration foundations implemented |

They should not yet be interpreted as fully managed, production-ready SaaS products.

Production deployment would require additional work such as:

- authentication and authorization
- persistent production job management
- secrets management
- monitoring and observability
- evaluation datasets
- cost controls
- security review
- backup and recovery procedures
- deployment-specific infrastructure

---

# Responsible Use

AI-generated extraction, transcription, classification, and analysis can be incomplete or incorrect.

Outputs should be treated as decision-support material and verified by a human with suitable domain expertise.

Do not commit any of the following to this repository:

- API keys or credentials
- `.env` files
- private contracts
- customer catalogues
- sales recordings
- call transcripts
- personally identifiable information
- proprietary model files
- confidential business data

---

# Author

**Maedeh Torkian**

Applied AI & Machine Learning Engineer focused on AI agents, document intelligence, speech analysis, multimodal systems, and reliable business-oriented AI workflows.
