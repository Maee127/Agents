"""
Stage 4: raw extracted rows -> clean rows matching the Master Excel schema.

This is where real-world messiness gets handled:
- numbers that arrive as strings with commas/currency symbols
- duplicate rows (same SKU extracted twice, e.g. a row that spanned a page break)
- multi-line model names with stray whitespace/newlines
- missing required fields (a row with no SKU and no price is junk, not a product)

Deliberately separate from extractor.py: the extraction prompt's job is to
get the model to *see* the table correctly; this module's job is to make the
output trustworthy regardless of what the model returned.
"""
from __future__ import annotations

import re
from datetime import date

from src.config import MASTER_COLUMNS

# Maps the extractor's raw field names to Master Excel column names.
_FIELD_TO_COLUMN = {
    "sku": "SKU / Item Code",
    "model_name": "Model Name",
    "category": "Product Category",
    "width_mm": "Width (mm)",
    "depth_mm": "Depth (mm)",
    "height_mm": "Height (mm)",
    "net_weight_kg": "Net Weight (kg)",
    "gross_weight_kg": "Gross Weight (kg)",
    "volume_l": "Volume (L)",
    "power_supply": "Power Supply (V/Hz)",
    "power_consumption_w": "Power Consumption (W)",
    "refrigerant_gas": "Refrigerant Gas",
    "energy_class": "Energy Class",
    "temperature_range": "Temperature Range (C)",
    "list_price": "List Price",
    "currency": "Currency",
    "source_page": "Source Page",
}


def _clean_number(value) -> float | None:
    """
    Coerce a price/dimension/weight value to a float.

    Handles the common real-world formats: "1.250,50" (EU), "1,250.50" (US),
    "1250.5", "EUR 1250,50", plain numbers, and None/empty.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    text = re.sub(r"[^\d.,\-]", "", text)  # strip currency symbols, spaces, letters
    if not text:
        return None

    # Disambiguate EU (1.250,50) vs US (1,250.50) formatting by looking at
    # which separator appears last — that's the decimal point.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # Only a comma present. If there's exactly one comma followed by
        # 1-2 digits, it's almost certainly a decimal separator (EU style:
        # "210,5" = 210.5, "8450,00" = 8450.00). Multiple commas, or a comma
        # followed by 3 digits, means thousands separator (e.g. "8,450" = 8450).
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def _clean_text(value) -> str | None:
    """Collapse whitespace/newlines (common in multi-line model names) and strip."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _row_key(row: dict) -> tuple:
    """Identity used for de-duplication: same SKU + same price = same product."""
    return (row.get("SKU / Item Code"), row.get("List Price"))


def normalize_rows(
    raw_rows: list[dict],
    brand: str,
    price_list_version: str = "",
    price_list_date: str | None = None,
) -> list[dict]:
    """
    Convert raw extractor rows into clean rows matching MASTER_COLUMNS.

    Args:
        raw_rows: output of extractor.extract_pages()
        brand: brand name to stamp on every row
        price_list_version: free-text version label, e.g. "2026"
        price_list_date: ISO date string; defaults to today if not given

    Returns:
        Deduplicated, cleaned rows — each a dict with exactly MASTER_COLUMNS keys.
    """
    price_list_date = price_list_date or date.today().isoformat()

    cleaned_rows: list[dict] = []
    seen_keys: set[tuple] = set()
    dropped_count = 0

    for raw in raw_rows:
        row = {col: None for col in MASTER_COLUMNS}
        row["Brand"] = brand
        row["Price List Version"] = price_list_version
        row["Price List Date"] = price_list_date

        for field, column in _FIELD_TO_COLUMN.items():
            value = raw.get(field)
            if column in ("List Price", "Width (mm)", "Depth (mm)", "Height (mm)",
                          "Net Weight (kg)", "Gross Weight (kg)", "Volume (L)",
                          "Power Consumption (W)"):
                row[column] = _clean_number(value)
            elif column == "Source Page":
                row[column] = value
            else:
                row[column] = _clean_text(value)

        # A row with neither a SKU nor a price isn't a usable product row —
        # most likely a misclassified header/legend line that slipped through.
        if not row["SKU / Item Code"] and row["List Price"] is None:
            dropped_count += 1
            continue

        key = _row_key(row)
        if key in seen_keys:
            dropped_count += 1
            continue
        seen_keys.add(key)

        row["Notes"] = "" if row["Notes"] is None else row["Notes"]
        cleaned_rows.append(row)

    if dropped_count:
        print(f"[normalizer] dropped {dropped_count} invalid/duplicate row(s) for {brand}")

    return cleaned_rows
