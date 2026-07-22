"""
Pipeline: the single entry point that wires ingestion -> chunking ->
analyzer into one call.

This file contains no real logic of its own -- it just sequences the
three modules and translates their errors into one consistent shape
the API layer (week 2) can rely on.
"""

from dataclasses import dataclass, field
from typing import Callable

from dotenv import load_dotenv

from ingestion import ingest_document, IngestionError
from chunking import chunk_document
from analyzer import analyze_chunk, AnalyzerError, ClauseVerdict
from local_llm import LocalLLMClient

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


def _make_llm_client() -> LocalLLMClient:
    return LocalLLMClient()


def analyze_contract(
    file_path: str,
    client: LocalLLMClient | None = None,
    model: str = "qwen2.5-7b",
    progress_callback: Callable[[int, int], None] | None = None,
) -> ContractReport:
    """
    Run the full pipeline on a single contract file.

    Raises PipelineError if the document itself can't be read.
    Per-clause failures are collected in failed_chunk_indices, never
    raised -- one bad clause never takes down the whole report.

    progress_callback, if given, is called as (chunks_done, chunks_total)
    after each chunk finishes (successfully or not), so callers like the
    web API can report live progress.
    """
    if client is None:
        client = _make_llm_client()

    try:
        text = ingest_document(file_path)
    except IngestionError as e:
        raise PipelineError(str(e), original=e) from e

    chunks = chunk_document(text)
    report = ContractReport(file_path=file_path)

    total = len(chunks)
    if progress_callback is not None:
        progress_callback(0, total)

    for done, chunk in enumerate(chunks, start=1):
        try:
            verdict = analyze_chunk(chunk, client, model=model)
            report.verdicts.append(verdict)
        except AnalyzerError:
            report.failed_chunk_indices.append(chunk.index)
        if progress_callback is not None:
            progress_callback(done, total)

    return report
