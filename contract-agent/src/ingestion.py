"""
Document ingestion: turn an uploaded file into clean, extractable text.

Handles .txt and .pdf. Detects likely scanned/image-based PDFs (no
embedded text) and fails with a specific, client-friendly error instead
of silently passing empty text downstream.
"""

from pathlib import Path
from pypdf import PdfReader


class IngestionError(Exception):
    """Base class for all ingestion failures."""


class UnsupportedFormatError(IngestionError):
    """Raised when the file extension isn't supported yet."""


class EmptyDocumentError(IngestionError):
    """Raised when the file has no extractable content at all."""


class ScannedDocumentError(IngestionError):
    """
    Raised when a PDF is very likely a scanned image (little or no
    embedded text per page). Known v1 limitation -- message says so
    clearly rather than crashing silently.
    """


MIN_CHARS_PER_PAGE = 50


def ingest_document(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        text = _ingest_txt(path)
    elif suffix == ".pdf":
        text = _ingest_pdf(path)
    else:
        raise UnsupportedFormatError(
            f"'{suffix}' files aren't supported yet. "
            "Please upload a .pdf or .txt file."
        )

    cleaned = _clean_text(text)

    if not cleaned.strip():
        raise EmptyDocumentError(
            "No readable text was found in this document."
        )

    return cleaned


def _ingest_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _ingest_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    num_pages = len(reader.pages)

    if num_pages == 0:
        raise EmptyDocumentError("This PDF has no pages.")

    page_texts = []
    for page in reader.pages:
        page_texts.append(page.extract_text() or "")

    total_chars = sum(len(t) for t in page_texts)
    avg_chars_per_page = total_chars / num_pages

    if avg_chars_per_page < MIN_CHARS_PER_PAGE:
        raise ScannedDocumentError(
            "This looks like a scanned or image-based PDF with no "
            "embedded text. OCR support isn't available yet -- for "
            "now, please upload a text-based PDF or a .txt copy."
        )

    return "\n\n".join(page_texts)


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if line == "":
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False
    return "\n".join(cleaned_lines).strip()
