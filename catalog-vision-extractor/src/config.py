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

# --- Page classification labels -----------------------------------------

PAGE_TYPES = ("intro", "spec", "drawing", "price_table")
TARGET_PAGE_TYPE = "price_table"

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
