"""
Stage 2: page image -> page type.

Classifies each rendered page as one of: intro, spec, drawing, price_table.
Only price_table pages are passed on to the extractor — this is what lets the
pipeline skip the marketing pages and spec sheets without a human looking at
every single page first.

Results are cached per (page-hash, prompt+model) since classification never
changes for an unchanged page image and an unchanged prompt.

A page whose classification fails (after retries) is marked with the
pipeline-level type "error" instead of crashing the whole run — on a
100-page catalogue, one bad response must not throw away the other 99.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydantic import ValidationError

from src.cache import context_hash, get_cached, set_cached
from src.config import ERROR_PAGE_TYPE, MAX_TOKENS_CLASSIFY, MAX_WORKERS, active_model
from src.rasterizer import RenderedPage
from src.schemas import PageClassification
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


def _cache_ctx() -> str:
    return context_hash(CLASSIFY_PROMPT, active_model())


def _parse_classification(raw_response: str) -> dict:
    """Extract and validate the JSON object from the model's response."""
    match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find JSON in classifier response: {raw_response!r}")

    try:
        result = PageClassification.model_validate(json.loads(match.group(0)))
    except ValidationError as exc:
        raise ValueError(f"Invalid classifier response: {exc}") from exc

    return result.model_dump()


def classify_page(page: RenderedPage, use_cache: bool = True) -> dict:
    """
    Classify a single rendered page.

    Returns: {"page_type": str, "confidence": float, "page_number": int}
    """
    ctx = _cache_ctx()
    if use_cache:
        cached = get_cached(CACHE_STAGE, page.page_hash, ctx)
        if cached is not None:
            return {**cached, "page_number": page.page_number}

    raw_response = call_vision(CLASSIFY_PROMPT, page.image_bytes, MAX_TOKENS_CLASSIFY)
    result = _parse_classification(raw_response)

    if use_cache:
        set_cached(CACHE_STAGE, page.page_hash, ctx, result)

    return {**result, "page_number": page.page_number}


def classify_pages(pages: list[RenderedPage], use_cache: bool = True) -> list[dict]:
    """
    Classify pages concurrently, returning one result dict per page in
    document order. Pages whose classification fails are marked with
    page_type "error" (confidence 0.0) rather than aborting the run.
    """
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(classify_page, page, use_cache): page for page in pages
        }
        for future in as_completed(futures):
            page = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 — isolate per-page failures
                print(f"[classifier] page {page.page_number} failed: {exc}")
                results.append(
                    {
                        "page_type": ERROR_PAGE_TYPE,
                        "confidence": 0.0,
                        "page_number": page.page_number,
                    }
                )

    results.sort(key=lambda r: r["page_number"])
    return results
