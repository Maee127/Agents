"""
Stage 3: price_table page image -> structured JSON.

This is the core of the pipeline. A price_table page typically contains
several product rows; we ask the vision model to return ALL of them as a
JSON array in one call, rather than one call per row (much cheaper, and the
model has full table context to disambiguate columns).

The schema requested here intentionally mirrors the raw catalogue fields,
not the final Master Excel columns — normalizer.py does that translation,
so this prompt can stay stable even if the master schema changes later.
"""
from __future__ import annotations

import json
import re

from src.cache import get_cached, set_cached
from src.rasterizer import RenderedPage
from src.vision_client import call_vision

CACHE_STAGE = "extract"

EXTRACTION_PROMPT = """You are looking at one page from a commercial kitchen \
equipment price catalogue. This page contains a price table. Extract EVERY \
product row you can see into a JSON array.

For each product, extract these fields (use null if a field is not present \
on this page — do not guess or invent values):

- "sku": the SKU / item / model code (string)
- "model_name": the product model name, even if it spans multiple lines (string)
- "category": product category or family if shown on this page, e.g. \
"Refrigerator", "Oven" (string or null)
- "width_mm": width in millimeters (number or null)
- "depth_mm": depth in millimeters (number or null)
- "height_mm": height in millimeters (number or null)
- "net_weight_kg": net weight in kilograms (number or null)
- "gross_weight_kg": gross weight in kilograms (number or null)
- "volume_l": capacity/volume in liters (number or null)
- "power_supply": voltage/frequency as written, e.g. "230V/50Hz" (string or null)
- "power_consumption_w": power consumption in watts (number or null)
- "refrigerant_gas": refrigerant gas code if shown, e.g. "R290" (string or null)
- "energy_class": energy efficiency class if shown, e.g. "A+" (string or null)
- "temperature_range": operating temperature range as written, e.g. "-2/+8C" (string or null)
- "list_price": the list price as a plain number, no currency symbol or \
thousands separators (number or null)
- "currency": the currency symbol or code shown next to the price, e.g. \
"EUR" or "$" (string or null)

Rules:
- If units are mixed on the page (e.g. inches alongside mm), prefer mm/kg/W —
  convert if both are shown, otherwise use what's given and note it isn't mm
  by leaving width_mm null.
- Skip header/legend rows that don't represent an actual product.
- If the same SKU repeats due to a wrapped/continued row, merge it into one entry.
- Respond with ONLY a JSON array, no other text, no markdown code fences.

Example response format:
[
  {"sku": "ABC-123", "model_name": "Example Unit 60", "category": "Oven", \
"width_mm": 600, "depth_mm": 700, "height_mm": 850, "net_weight_kg": 45.5, \
"gross_weight_kg": 50.0, "volume_l": null, "power_supply": "230V/50Hz", \
"power_consumption_w": 3200, "refrigerant_gas": null, "energy_class": "A", \
"temperature_range": null, "list_price": 1250.00, "currency": "EUR"}
]
"""


def _parse_extraction(raw_response: str) -> list[dict]:
    """Extract the JSON array from the model's response, tolerating stray text/fences."""
    cleaned = raw_response.strip()
    # Strip markdown code fences if the model added them despite instructions
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE)

    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find a JSON array in extractor response: {raw_response!r}")

    rows = json.loads(match.group(0))
    if not isinstance(rows, list):
        raise ValueError("Extractor response JSON was not a list")
    return rows


def extract_page(page: RenderedPage, use_cache: bool = True) -> list[dict]:
    """
    Extract all product rows from a single price_table page image.

    Returns a list of raw row dicts (schema described in EXTRACTION_PROMPT),
    each tagged with the source page number for traceability.
    """
    if use_cache:
        cached = get_cached(CACHE_STAGE, page.page_hash)
        if cached is not None:
            return cached

    raw_response = call_vision(EXTRACTION_PROMPT, page.image_bytes)
    rows = _parse_extraction(raw_response)

    for row in rows:
        row["source_page"] = page.page_number

    if use_cache:
        set_cached(CACHE_STAGE, page.page_hash, rows)

    return rows


def extract_pages(pages: list[RenderedPage], use_cache: bool = True) -> list[dict]:
    """Extract rows from a list of price_table pages, flattening into one list."""
    all_rows: list[dict] = []
    for page in pages:
        all_rows.extend(extract_page(page, use_cache=use_cache))
    return all_rows
