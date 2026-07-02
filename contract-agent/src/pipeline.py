"""
Pipeline: the single entry point that wires ingestion -> chunking ->
analyzer into one call.

This file contains no real logic of its own -- it just sequences the
three modules and translates their errors into one consistent shape
the API layer (week 2) can rely on.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI

from ingestion import ingest_document, IngestionError
from chunking import chunk_document
from analyzer import analyze_chunk, AnalyzerError, ClauseVerdict

load_dotenv()


@dataclass
class ContractReport:
    file_path: str
    verdicts: list[ClauseVerdict] = field(default_factory=list)
    failed_chunk_indices: list[int] = field(default_factory=list)

    @property
    def high_risk_count(self) -> int:
        return sum(1 for v in self.verdicts if v.risk_level == "high")

    @property
    def medium_risk_count(self) -> int:
        return sum(1 for v in self.verdicts if v.risk_level == "medium")


class PipelineError(Exception):
    def __init__(self, message: str, original: Exception):
        super().__init__(message)
        self.original = original


def _make_groq_client() -> OpenAI:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found. Please set it in your .env file."
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )


def analyze_contract(
    file_path: str,
    client: OpenAI | None = None,
    model: str = "llama-3.3-70b-versatile",
) -> ContractReport:
    """
    Run the full pipeline on a single contract file.

    Raises PipelineError if the document itself can't be read.
    Per-clause failures are collected in failed_chunk_indices, never
    raised -- one bad clause never takes down the whole report.
    """
    if client is None:
        client = _make_groq_client()

    try:
        text = ingest_document(file_path)
    except IngestionError as e:
        raise PipelineError(str(e), original=e) from e

    chunks = chunk_document(text)
    report = ContractReport(file_path=file_path)

    for chunk in chunks:
        try:
            verdict = analyze_chunk(chunk, client, model=model)
            report.verdicts.append(verdict)
        except AnalyzerError:
            report.failed_chunk_indices.append(chunk.index)

    return report
