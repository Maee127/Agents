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

import anthropic

from ingestion import ingest_document, IngestionError
from chunking import chunk_document
from analyzer import analyze_chunk, AnalyzerError, ClauseVerdict


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
    client: anthropic.Anthropic | None = None,
    model: str = "claude-sonnet-4-6",
) -> ContractReport:
    """
    Run the full pipeline on a single contract file.

    Raises PipelineError if the document itself can't be read
    (unsupported format, scanned PDF, empty file). Per-clause analysis
    failures do NOT raise -- they're collected in
    ContractReport.failed_chunk_indices so one bad clause never takes
    down the whole report.
    """
    if client is None:
        client = anthropic.Anthropic()

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
            # One clause failing to parse shouldn't sink the whole
            # report -- log and continue. The caller can decide how
            # to surface "3 of 24 clauses couldn't be analyzed."
            report.failed_chunk_indices.append(chunk.index)

    return report
