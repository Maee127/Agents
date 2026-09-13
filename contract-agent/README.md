# Contract Agent

A local-first AI system for clause-level contract review, structured risk analysis, and evidence-aware decision support.

The Contract Agent processes PDF and TXT agreements, identifies clause boundaries, analyzes each clause with a locally hosted language model, validates structured findings against the source text, and exposes the results through a FastAPI backend and lightweight browser interface.

The goal is to make first-pass contract review faster and more consistent while keeping final legal judgment with a qualified human reviewer.

![Contract Agent Architecture](../docs/images/contract_agent_architecture.png)

---

## Business Problem

Long contracts are difficult to review consistently, especially when important obligations, unusual terms, and potential risks are distributed across many pages.

This creates several common problems:

- reviewers spend significant time locating relevant clauses;
- important obligations may be overlooked during manual review;
- risk assessment can vary between reviewers;
- supporting evidence may become separated from the conclusion;
- repetitive first-pass review consumes time that could be spent on higher-value legal analysis.

The Contract Agent is designed to support a more structured and reviewable first-pass workflow.

---

## Business Value

Its intended value is to help users:

- identify and separate contract clauses automatically;
- surface obligations, summaries, and potential risk signals;
- preserve supporting source text behind findings;
- review contracts through a consistent structured schema;
- isolate failures so one problematic clause does not stop the entire analysis;
- reduce repetitive review work while keeping final judgment with a qualified human reviewer.

The system is intended as **decision support, not as a replacement for professional legal advice**.

---

## Current Workflow

```text
PDF / TXT Contract
        ↓
Document Ingestion
        ↓
Clause-Aware Chunking
        ↓
Local LLM Analysis
        ↓
Structured Output Validation
        ↓
Source-Evidence Verification
        ↓
Background Processing
        ↓
FastAPI / Browser Results
```

---

## Implemented Features

- PDF and TXT document ingestion
- detection of empty and unsupported documents
- scanned-document handling
- structural clause splitting
- sentence-boundary fallback
- local Qwen2.5-7B inference through Transformers
- structured clause verdicts
- clause type and summary outputs
- obligation extraction
- risk-level classification
- source-quote verification
- rejection of unsupported risk evidence
- per-clause failure isolation
- progress callbacks
- in-memory background job processing
- upload type and size validation
- FastAPI endpoints
- lightweight browser interface
- unit and integration test organization

---

## Engineering Highlights

### Local-First Inference

Contract content can be analyzed using a locally stored Qwen2.5-7B model rather than requiring contract text to be sent to a hosted inference provider.

### Structured AI Outputs

Model responses are converted into structured findings rather than being treated as unrestricted free-form text.

This makes downstream validation and presentation more predictable.

### Evidence Verification

Risk findings are checked against the original clause text so unsupported evidence can be rejected rather than silently accepted.

### Clause-Level Failure Isolation

A failure while analyzing one clause does not necessarily terminate the analysis of the entire contract.

### Document-Aware Chunking

The system first attempts to preserve structural contract boundaries and falls back to sentence-aware splitting when necessary.

### Human Review by Design

The system exposes findings as reviewable decision-support material rather than presenting model output as authoritative legal judgment.

---

## Tech Stack

### Application

- Python 3.13
- FastAPI
- Uvicorn

### AI and NLP

- Qwen2.5-7B
- Transformers
- PyTorch
- Accelerate

### Document Processing

- PyPDF

### Validation and Configuration

- Pydantic
- python-dotenv

### Engineering

- pytest
- local model execution
- structured validation
- background processing

---

## Installation

### Requirements

- Python 3.13
- sufficient local resources for the selected Qwen2.5-7B model
- compatible local model files

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate

# Windows:
# .venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure required environment variables locally.

Do not commit `.env` files or credentials.

---

## Running the Application

Start the FastAPI application:

```bash
uvicorn app.main:app --reload
```

Open the browser interface:

```text
http://127.0.0.1:8000
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

Upload a supported `.pdf` or `.txt` contract to begin clause-level analysis.

> The first analysis may take longer because the local language model must be loaded into memory.

---

## Testing

Run the test suite with:

```bash
pytest
```

Tests are organized around the document-processing, analysis, validation, and application layers.

---

## Project Structure

```text
contract-agent/
├── app/
├── src/
├── tests/
├── train-agent.ipynb
├── check_files.py
├── requirements.txt
└── README.md
```

---

## Current Limitations

The current implementation is a local MVP and has not been validated as a production legal-review system.

Current limitations include:

- analysis quality depends on document structure and text-extraction quality;
- scanned or visually complex documents may require additional preprocessing;
- local language-model outputs can still be incomplete or incorrect;
- legal interpretation varies by jurisdiction and contract context;
- the current background-processing model is suitable for local MVP use rather than high-scale production workloads;
- authentication, authorization, persistent job management, monitoring, and production deployment controls are not yet complete.

All findings should be reviewed by a qualified legal professional before they are used for legal or business decisions.

---

## Future Development

Potential future work includes:

- support for additional document formats such as DOCX and RTF;
- multilingual contract analysis;
- persistent job storage;
- authentication and access control;
- configurable risk policies;
- batch contract processing;
- contract-management-system integration;
- production monitoring and observability;
- comparative analysis across approved contract collections.

---

## Responsible Use

Contract Agent provides automated analysis for educational and decision-support purposes.

AI-generated findings may be incomplete, incorrect, or inappropriate for a particular jurisdiction or contract context.

**The system does not provide legal advice.**

Qualified legal professionals should review contracts and model-generated findings before legal or business decisions are made.
