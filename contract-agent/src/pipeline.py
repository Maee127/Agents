"""
Pipeline: the single entry point that wires ingestion -> chunking ->
analyzer into one call.

This file intentionally contains no real logic of its own -- it just
sequences the three modules and translates their errors into one
consistent shape the API layer (week 2) can rely on. If you find
yourself adding actual parsing/prompting logic here, it belongs in
one of the three modules instead.
"""

from dataclasses import dataclass, field
import os
from openai import OpenAI
from typing import Optional

from ingestion import ingest_document, IngestionError
from chunking import chunk_document
from analyzer import analyze_chunk, AnalyzerError, ClauseVerdict

from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

@dataclass
class ContractReport:
    file_path: str
    verdicts: list[ClauseVerdict] = field(default_factory=list)
    # Chunks that failed analysis aren't silently dropped -- they're
    # tracked so the API/UI can show "N of M clauses analyzed" honestly
    # rather than presenting a partial report as if it were complete.
    failed_chunk_indices: list[int] = field(default_factory=list)

    @property
    def high_risk_count(self) -> int:
        return sum(1 for v in self.verdicts if v.risk_level == "high")

    @property
    def medium_risk_count(self) -> int:
        return sum(1 for v in self.verdicts if v.risk_level == "medium")


class PipelineError(Exception):
    """Raised for failures that happen before per-clause analysis even
    starts (ingestion failures). Carries the original error so the
    caller can show the same specific, honest message ingestion.py
    already wrote -- this wrapper exists for a uniform error type at
    the pipeline boundary, not to replace the underlying message."""

    def __init__(self, message: str, original: Exception):
        super().__init__(message)
        self.original = original


def analyze_contract(
    file_path: str,
    client: Optional[OpenAI] = None,
    model: str = "llama-3.3-70b-versatile",  # Groq's best reasoning model
) -> ContractReport:
    """
    Run the full pipeline on a single contract file using Groq API.

    Raises PipelineError if the document itself can't be read
    (unsupported format, scanned PDF, empty file). Per-clause analysis
    failures do NOT raise -- they're collected in
    ContractReport.failed_chunk_indices so one bad clause never takes
    down the whole report.
    """
    # Initialize Groq client if not provided
    if client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. Please set it in your .env file"
            )
        
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )

    # Step 1: Ingest the document
    try:
        text = ingest_document(file_path)
    except IngestionError as e:
        raise PipelineError(str(e), original=e) from e

    # Step 2: Chunk the document into clauses
    chunks = chunk_document(text)
    
    # Optional: Log chunking results
    print(f"📄 Document chunked into {len(chunks)} clauses")

    # Step 3: Analyze each chunk and build the report
    report = ContractReport(file_path=file_path)
    
    for chunk in chunks:
        try:
            # This function handles the API call for each chunk
            verdict = analyze_chunk(chunk, client, model=model)
            report.verdicts.append(verdict)
            print(f"  ✓ Clause {chunk.index}: {verdict.risk_level} risk")
        except AnalyzerError:
            # One clause failing to parse shouldn't sink the whole
            # report -- log and continue. The caller can decide how
            # to surface "3 of 24 clauses couldn't be analyzed."
            report.failed_chunk_indices.append(chunk.index)
            print(f"  ✗ Clause {chunk.index}: Analysis failed")

    print(f"\n✅ Analysis complete!")
    print(f"   - {len(report.verdicts)} clauses analyzed")
    print(f"   - {len(report.failed_chunk_indices)} clauses failed")
    print(f"   - High risk: {report.high_risk_count}")
    print(f"   - Medium risk: {report.medium_risk_count}")

    return report
