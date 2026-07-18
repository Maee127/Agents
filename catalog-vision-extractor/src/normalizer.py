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

    Handles common real-world number formats:
    - EU format: "1.250,50" (period = thousands, comma = decimal)
    - US format: "1,250.50" (comma = thousands, period = decimal)
    - Plain: "1250.5", "1250", "-45.5"
    - With currency: "EUR 1250,50", "$1,250.50", "1.250,50 €"
    - Edge cases: "210,5" (EU decimal), "8,450" (US thousands)

    Algorithm:
    1. Return None for None/empty inputs
    2. Strip non-numeric characters (currency symbols, spaces, letters)
    3. Identify which separator (comma or period) is the decimal point:
       - If both exist: last separator is decimal
       - If only comma with 1-2 trailing digits: comma is decimal
       - Otherwise: interpret as thousands separator
    4. Convert to float, preserving sign

    Returns:
        Float value or None if unparseable.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    
    # Step 1: Remove all non-numeric characters except dots, commas, and minus sign
    # This handles: "EUR 1250,50" → "1250,50", "$1,250.50" → "1250.50", "-45.5" → "-45.5"
    text = re.sub(r"[^\d.,\-]", "", text)
    if not text:
        return None

    # Handle negative numbers: extract sign and process absolute value
    is_negative = text.startswith("-")
    if is_negative:
        text = text[1:]

    # Step 2: Disambiguate decimal separator
    # Both separators present: last one is decimal point
    if "," in text and "." in text:
        comma_pos = text.rfind(",")
        period_pos = text.rfind(".")
        
        if comma_pos > period_pos:
            # EU format: "1.250,50" → remove thousands dots, replace decimal comma
            text = text.replace(".", "").replace(",", ".")
        else:
            # US format: "1,250.50" → remove thousands commas
            text = text.replace(",", "")
    
    elif "," in text:
        # Only commas present: disambiguate by digit count after comma
        parts = text.split(",")
        
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            # EU decimal separator: "210,5" or "8450,00"
            # Exactly 1-2 digits after comma = decimal point
            text = text.replace(",", ".")
        else:
            # US thousands separator: "8,450" or multiple commas "1,000,000"
            text = text.replace(",", "")
    
    # else: only periods or no separators → Python float() handles it

    try:
        result = float(text)
        return -result if is_negative else result
    except ValueError:
        return None


def _clean_text(value) -> str | None:
    """
    Clean text fields: collapse whitespace/newlines and strip.
    
    Handles multi-line model names that arrive with embedded newlines:
    "Combi\nOven\n  60" → "Combi Oven 60"
    """
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _row_key(row: dict) -> tuple:
    """
    Identity used for de-duplication: same SKU + same price = same product.
    
    This tuple is used as a key in a set to detect duplicate rows.
    Rows with identical SKU and List Price are considered duplicates
    (e.g., a row that spanned a page break and was extracted twice).
    """
    return (row.get("SKU / Item Code"), row.get("List Price"))


def normalize_rows(
    raw_rows: list[dict],
    brand: str,
    price_list_version: str = "",
    price_list_date: str | None = None,
) -> list[dict]:
    """
    Convert raw extractor rows into clean rows matching MASTER_COLUMNS.

    Processing steps:
    1. Initialize each row with MASTER_COLUMNS (all None initially)
    2. Stamp Brand, Price List Version, and Date
    3. Map extractor field names to column names
    4. Apply appropriate cleaning (numbers, text, or passthrough)
    5. Drop junk rows (no SKU AND no price)
    6. Deduplicate by SKU+price key
    7. Log how many rows were dropped

    Args:
        raw_rows: output of extractor.extract_pages() — list of dicts with
                  raw field names (sku, model_name, list_price, etc.)
        brand: brand name to stamp on every row (from CLI --brand argument)
        price_list_version: free-text version label, e.g. "2026" (from CLI --version)
        price_list_date: ISO date string; defaults to today if not given

    Returns:
        Deduplicated, cleaned rows — each a dict with exactly MASTER_COLUMNS keys,
        ready to write to Excel.
    """
    price_list_date = price_list_date or date.today().isoformat()

    cleaned_rows: list[dict] = []
    seen_keys: set[tuple] = set()
    dropped_count = 0

    for raw in raw_rows:
        # Initialize with all columns set to None
        row = {col: None for col in MASTER_COLUMNS}
        
        # Stamp fixed fields
        row["Brand"] = brand
        row["Price List Version"] = price_list_version
        row["Price List Date"] = price_list_date

        # Map and clean extractor fields to Excel columns
        for field, column in _FIELD_TO_COLUMN.items():
            value = raw.get(field)
            
            # Numeric fields: use _clean_number() to handle all locale formats
            if column in (
                "List Price",
                "Width (mm)",
                "Depth (mm)",
                "Height (mm)",
                "Net Weight (kg)",
                "Gross Weight (kg)",
                "Volume (L)",
                "Power Consumption (W)",
            ):
                row[column] = _clean_number(value)
            
            # Source Page: keep as-is (integer from extractor)
            elif column == "Source Page":
                row[column] = value
            
            # All other text fields: collapse whitespace and strip
            else:
                row[column] = _clean_text(value)

        # Validation: drop rows with neither SKU nor price
        # These are typically misclassified header/legend rows
        if not row["SKU / Item Code"] and row["List Price"] is None:
            dropped_count += 1
            continue

        # Deduplication: skip if we've already seen this SKU+price combination
        key = _row_key(row)
        if key in seen_keys:
            dropped_count += 1
            continue
        seen_keys.add(key)

        # Ensure Notes is never None (empty string is the default)
        row["Notes"] = "" if row["Notes"] is None else row["Notes"]
        cleaned_rows.append(row)

    if dropped_count:
        print(f"[normalizer] dropped {dropped_count} invalid/duplicate row(s) for {brand}")

    return cleaned_rows
