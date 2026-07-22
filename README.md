# AI Agents Portfolio

A growing portfolio of practical AI-agent systems built to turn unstructured documents into structured, useful, and reviewable outputs.

This repository currently contains two independent projects:

1. **Catalog Vision Extractor** — a multimodal document-processing pipeline that converts complex commercial PDF catalogues into a normalized Excel database.
2. **Contract Agent** — a local-LLM contract review application that ingests agreements, analyzes clauses, assigns risk levels, and exposes the results through a FastAPI-based web interface.

The projects focus on real business workflows rather than isolated model demonstrations: document ingestion, classification, structured extraction, validation, caching, failure handling, APIs, testing, and user-facing delivery.

---

## Projects

| Project | Problem | Core approach | Current interface |
|---|---|---|---|
| [Catalog Vision Extractor](./catalog-vision-extractor) | Product and price data is trapped inside visually complex, inconsistent PDF catalogues. | Rasterize pages, classify them with a vision LLM, extract price-table rows, normalize the data, and merge the results into a master Excel workbook. | Command-line pipeline |
| [Contract Agent](./contract-agent) | Contracts are long, difficult to review, and easy to misunderstand. | Ingest PDF/TXT files, split them into clause-aware chunks, analyze each chunk with a local LLM, and return structured risk verdicts. | FastAPI API and lightweight web UI |

---

## 1. Catalog Vision Extractor

The **Catalog Vision Extractor** transforms multi-brand commercial-equipment catalogues into a consistent Excel dataset.

Traditional PDF parsers often fail on these documents because their layouts vary by brand and mix marketing pages, specifications, technical drawings, and price tables. This project treats every page as an image and uses a vision-capable language model to decide which pages matter before extracting structured product data.

### Pipeline

```text
PDF catalogue
    │
    ▼
Page rasterization
    │
    ▼
Vision-based page classification
    │
    ├── intro / specification / drawing ──► skipped
    │
    └── price_table
              │
              ▼
      Structured JSON extraction
              │
              ▼
      Normalization and validation
              │
              ▼
       Master Excel workbook
```

### Implemented capabilities

- PDF-to-image rasterization with PyMuPDF
- Vision-based page classification
- Structured extraction from price-table pages
- Anthropic and OpenAI vision-provider support
- Product-row normalization and validation
- Duplicate and malformed-row handling
- Page-hash caching for idempotent reprocessing
- Multi-brand export to a shared Excel workbook
- CLI support for one PDF or an entire input directory
- Unit tests for normalization behavior
- Documented output schema

### Main modules

```text
catalog-vision-extractor/
├── src/
│   ├── cache.py
│   ├── classifier.py
│   ├── config.py
│   ├── exporter.py
│   ├── extractor.py
│   ├── normalizer.py
│   ├── pipeline.py
│   ├── rasterizer.py
│   └── vision_client.py
├── docs/
│   └── schema.md
├── tests/
│   └── test_normalizer.py
├── README.md
└── requirements.txt
```

### Quick start

```bash
cd catalog-vision-extractor

python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Configure either an Anthropic or OpenAI API key in your local environment, then run:

```bash
python -m src.pipeline \
  --pdf data/input/acme_2026.pdf \
  --brand ACME \
  --version 2026
```

Process every PDF in the input directory:

```bash
python -m src.pipeline --all --version 2026
```

Force reprocessing without cached classification or extraction results:

```bash
python -m src.pipeline \
  --pdf data/input/acme_2026.pdf \
  --brand ACME \
  --no-cache
```

The generated workbook is written to:

```text
data/output/master_pricelist.xlsx
```

See the [project README](./catalog-vision-extractor/README.md) and [schema reference](./catalog-vision-extractor/docs/schema.md) for more detail.

---

## 2. Contract Agent

The **Contract Agent** is an MVP contract-analysis system designed around local inference.

It reads PDF or plain-text agreements, separates them into manageable clause-oriented chunks, analyzes each chunk with a local language model, and returns structured verdicts. Individual chunk failures are recorded instead of terminating the entire analysis.

A FastAPI layer exposes the pipeline through asynchronous-style jobs suitable for a single-process MVP. Uploaded contracts are processed by a dedicated worker thread, while the UI polls for status and per-clause progress.

### Application flow

```text
PDF or TXT contract
        │
        ▼
Document ingestion
        │
        ▼
Clause-aware chunking
        │
        ▼
Local LLM analysis
        │
        ▼
Structured clause verdicts
        │
        ├── risk level
        ├── explanation
        ├── obligations
        └── review findings
        │
        ▼
FastAPI job API + browser UI
```

### Implemented capabilities

- PDF and TXT ingestion
- Clause-oriented document chunking
- Local LLM client integration
- Structured per-clause risk analysis
- High- and medium-risk aggregation
- Graceful handling of failed chunks
- Progress callbacks during analysis
- FastAPI upload and job-status endpoints
- Background worker queue for local-model processing
- Lightweight static web interface
- Upload type and size validation
- Unit and integration test structure
- Training and experimentation notebook

### Main modules

```text
contract-agent/
├── app/
│   ├── main.py
│   └── static/
├── src/
│   ├── analyzer.py
│   ├── chunking.py
│   ├── ingestion.py
│   ├── local_llm.py
│   └── pipeline.py
├── tests/
│   ├── fixtures/
│   ├── integration/
│   ├── unit/
│   └── conftest.py
├── train-agent.ipynb
├── check_files.py
├── README.md
└── requirements.txt
```

### Quick start

The project targets Python 3.13 and expects a compatible local model service.

```bash
cd contract-agent

python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Then open the local application in your browser at:

```text
http://127.0.0.1:8000
```

Run the test suite:

```bash
pytest
```

Check the expected project files:

```bash
python check_files.py
```

See the [project README](./contract-agent/README.md) for project-specific notes.

> **Important:** This project provides automated analysis and educational support. It is not a substitute for review by a qualified legal professional.

---

## Technology Overview

### Languages and application layer

- Python
- Jupyter Notebook
- HTML
- FastAPI
- Uvicorn

### AI and document processing

- Anthropic API
- OpenAI API
- Local language models
- PyTorch
- Transformers
- PyPDF
- PyMuPDF
- Pydantic

### Data and output

- pandas
- openpyxl
- JSON
- Excel

### Engineering practices represented

- Modular pipeline architecture
- Provider abstraction
- Structured model outputs
- Input validation
- Caching and idempotency
- Fault isolation
- Background job processing
- Unit and integration testing
- CLI and HTTP interfaces
- Environment-based configuration

---

## Repository Structure

```text
Agents/
├── catalog-vision-extractor/
│   ├── docs/
│   ├── src/
│   ├── tests/
│   ├── README.md
│   └── requirements.txt
│
└── contract-agent/
    ├── app/
    ├── src/
    ├── tests/
    ├── train-agent.ipynb
    ├── README.md
    └── requirements.txt
```

Each project is self-contained and has its own dependencies, setup instructions, and documentation.

---

## Portfolio Goals

This repository documents my work in applied AI systems, particularly:

- AI agents for document-heavy workflows
- Multimodal and vision-LLM pipelines
- Local and API-hosted language-model integration
- Structured extraction from unstructured data
- Reliable orchestration around probabilistic models
- Business-facing AI prototypes with usable interfaces

The emphasis is not only on calling a model, but on building the surrounding system required to make model output operational: preprocessing, routing, schemas, validation, caching, error handling, tests, APIs, and export layers.

---

## Current Status

These projects are portfolio-scale implementations and continue to evolve.

- **Catalog Vision Extractor:** functional modular proof of concept with CLI orchestration, caching, normalization, testing, and Excel export.
- **Contract Agent:** working MVP architecture with local-model analysis, a FastAPI job layer, a lightweight UI, and test organization.

Planned improvements include broader evaluation datasets, stronger extraction and risk-analysis metrics, persistent job storage, authentication, deployment configuration, richer observability, and production-grade security controls.

---

## Responsible Use

AI-generated document analysis can be incomplete or incorrect. Outputs should be treated as decision-support material and verified by a human with appropriate domain expertise.

Do not commit API keys, credentials, private contracts, customer catalogues, or other sensitive data to the repository.
