"""
Stage 2: page image -> page type.

Classifies each rendered page as one of: intro, spec, drawing, price_table.
Only price_table pages are passed on to the extractor — this is what lets the
pipeline skip the marketing pages and spec sheets without a human looking at
every single page first.

Results are cached per page-hash since classification never changes for an
unchanged page image.
"""
from __future__ import annotations

import json
import re

from src.cache import get_cached, set_cached
from src.config import PAGE_TYPES
from src.rasterizer import RenderedPage
from src.vision_client import call_vision

CACHE_STAGE = "classify"

CLASSIFY_PROMPT = """You are looking at one page from a commercial kitchen \
equipment price catalogue (PDF export). Classify this page into EXACTLY ONE \
of these categories:

- "intro": full-bleed marketing or cover page, brand imagery, no product data
- "spec": multilingual product description / feature text, no price table
- "drawing": technical drawing or dimensional diagram of a product, no prices
- "price_table": a table of products with SKU codes, model names, and a \
list price column (THIS IS THE TARGET — also use this if the page mixes a \
price table with some dimensions or specs alongside it)

Respond with ONLY a JSON object, no other text, in this exact format:
{"page_type": "<one of: intro, spec, drawing, price_table>", "confidence": <0.0-1.0>}
"""


def _parse_classification(raw_response: str) -> dict:
    """Extract the JSON object from the model's response, tolerating stray text/fences."""
    match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find JSON in classifier response: {raw_response!r}")
    result = json.loads(match.group(0))

    page_type = result.get("page_type")
    if page_type not in PAGE_TYPES:
        raise ValueError(f"Unexpected page_type from classifier: {page_type!r}")

    return {"page_type": page_type, "confidence": float(result.get("confidence", 0.0))}


def classify_page(page: RenderedPage, use_cache: bool = True) -> dict:
    """
    Classify a single rendered page.

    Returns: {"page_type": str, "confidence": float, "page_number": int}
    """
    if use_cache:
        cached = get_cached(CACHE_STAGE, page.page_hash)
        if cached is not None:
            return {**cached, "page_number": page.page_number}

    raw_response = call_vision(CLASSIFY_PROMPT, page.image_bytes)
    result = _parse_classification(raw_response)

    if use_cache:
        set_cached(CACHE_STAGE, page.page_hash, result)

    return {**result, "page_number": page.page_number}


def classify_pages(pages: list[RenderedPage], use_cache: bool = True) -> list[dict]:
    """Classify a list of pages, returning one result dict per page."""
    return [classify_page(page, use_cache=use_cache) for page in pages]
