"""
Central configuration for the pipeline: API provider selection, file paths,
and the master Excel column schema. Everything else imports from here so
there's exactly one place to change settings.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths -------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
CACHE_DIR = DATA_DIR / "cache"

MASTER_EXCEL_PATH = OUTPUT_DIR / "master_pricelist.xlsx"

for _dir in (INPUT_DIR, OUTPUT_DIR, CACHE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# --- Vision provider -----------------------------------------------------

VISION_PROVIDER = os.getenv("VISION_PROVIDER", "anthropic").lower()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

RENDER_DPI = int(os.getenv("RENDER_DPI", "175"))

# Classification needs a tiny JSON object; extraction can need thousands of
# tokens for a dense table (30 rows x 17 fields), so the two budgets differ.
MAX_TOKENS_CLASSIFY = 300
MAX_TOKENS_EXTRACT = 8000

# Parallel vision calls per stage. Each call is independent (one page each),
# so a small thread pool gives a near-linear speedup on large catalogues.
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))

# Transient API failures (rate limits, timeouts) are retried this many times
# with exponential backoff before a page is marked as failed.
API_MAX_RETRIES = 3
API_RETRY_BASE_DELAY = 2.0  # seconds; doubles per attempt

# Pages classified with confidence below this are listed for human review in
# the pipeline summary (they are still processed normally).
CONFIDENCE_REVIEW_THRESHOLD = 0.6


def active_model() -> str:
    """The model name for the currently selected provider (used in cache keys)."""
    return ANTHROPIC_MODEL if VISION_PROVIDER == "anthropic" else OPENAI_MODEL


# --- Page classification labels -----------------------------------------

PAGE_TYPES = ("intro", "spec", "drawing", "price_table")
TARGET_PAGE_TYPE = "price_table"

# Pipeline-level marker for pages whose classification call failed outright.
# Not a real page type — never sent to or returned by the model.
ERROR_PAGE_TYPE = "error"

# --- Master Excel schema --------------------------------------------------
# Single source of truth for column order. The normalizer fills these,
# the exporter writes them in exactly this order.

MASTER_COLUMNS = [
    "Brand",
    "SKU / Item Code",
    "Model Name",
    "Product Family / Series",
    "Product Category",
    "Width (mm)",
    "Depth (mm)",
    "Height (mm)",
    "Net Weight (kg)",
    "Gross Weight (kg)",
    "Volume (L)",
    "Power Supply (V/Hz)",
    "Power Consumption (W)",
    "Refrigerant Gas",
    "Energy Class",
    "Temperature Range (C)",
    "List Price",
    "Currency",
    "Price List Version",
    "Price List Date",
    "Source Page",
    "Notes",
]


def validate_config() -> None:
    """Raise a clear error early if the selected provider has no API key."""
    if VISION_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "VISION_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and fill in your key."
        )
    if VISION_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise RuntimeError(
            "VISION_PROVIDER is 'openai' but OPENAI_API_KEY is not set. "
            "Copy .env.example to .env and fill in your key."
        )
    if VISION_PROVIDER not in ("anthropic", "openai"):
        raise RuntimeError(
            f"Unknown VISION_PROVIDER '{VISION_PROVIDER}'. Use 'anthropic' or 'openai'."
        )
