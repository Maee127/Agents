"""
Stage 1: PDF -> page images.

Uses PyMuPDF (imported as `pymupdf` — never `fitz`, which collides with an
unrelated PyPI package of the same name) rather than pdf2image/poppler so
there's no external binary dependency — just a pip install. Each page is
rendered to a PNG at a configurable DPI and returned alongside its page
number and a content hash (used downstream for caching).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.config import RENDER_DPI


@dataclass
class RenderedPage:
    page_number: int          # 1-indexed, matches what a human would call "page 5"
    image_bytes: bytes        # PNG bytes
    page_hash: str            # sha256 of image_bytes, used as the cache key


def rasterize_pdf(pdf_path: Path, dpi: int = RENDER_DPI) -> list[RenderedPage]:
    """
    Render every page of a PDF to a PNG image.

    Args:
        pdf_path: path to the source PDF.
        dpi: render resolution. ~150-200 is the sweet spot for price tables —
             high enough for the model to read small text, not so high that
             every page costs a fortune in vision tokens.

    Returns:
        One RenderedPage per page, in document order.
    """
    # Imported here rather than at module level so the rest of the pipeline
    # (and the test suite) can be imported without the PyMuPDF binary wheel.
    import pymupdf

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    zoom = dpi / 72  # PDF base unit is 72 dpi
    matrix = pymupdf.Matrix(zoom, zoom)

    pages: list[RenderedPage] = []
    with pymupdf.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix)
            image_bytes = pix.tobytes("png")
            page_hash = hashlib.sha256(image_bytes).hexdigest()
            pages.append(
                RenderedPage(
                    page_number=index + 1,
                    image_bytes=image_bytes,
                    page_hash=page_hash,
                )
            )
    return pages


def save_page_image(page: RenderedPage, out_dir: Path) -> Path:
    """Optional helper: persist a rendered page to disk for debugging/inspection."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page_{page.page_number:04d}.png"
    out_path.write_bytes(page.image_bytes)
    return out_path
