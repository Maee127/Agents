"""
Unit tests for normalizer.py — no API calls, no PDFs needed. These exercise
the exact kinds of messiness the job spec calls out: mixed number formats,
multi-line names, duplicate rows, junk rows with no SKU/price.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizer import _clean_number, _clean_text, normalize_rows


def test_clean_number_eu_format():
    assert _clean_number("1.250,50") == 1250.50


def test_clean_number_us_format():
    assert _clean_number("1,250.50") == 1250.50


def test_clean_number_plain():
    assert _clean_number("1250.5") == 1250.5


def test_clean_number_with_currency_symbol():
    assert _clean_number("EUR 1250,50") == 1250.50


def test_clean_number_none_and_empty():
    assert _clean_number(None) is None
    assert _clean_number("") is None
    assert _clean_number("n/a") is None


def test_clean_number_already_numeric():
    assert _clean_number(1250) == 1250.0
    assert _clean_number(1250.5) == 1250.5


def test_clean_number_eu_single_comma_decimal():
    # A single comma with 1-2 trailing digits is a decimal separator, not
    # a thousands separator — "210,5" kg means 210.5 kg, not 2105 kg.
    assert _clean_number("210,5") == 210.5
    assert _clean_number("8450,00") == 8450.0


def test_clean_number_thousands_separator_only():
    # A comma followed by exactly 3 digits with no decimal part is a
    # thousands separator, e.g. a price written as "8,450".
    assert _clean_number("8,450") == 8450.0



    assert _clean_text("Combi\nOven\n  60") == "Combi Oven 60"


def test_clean_text_none():
    assert _clean_text(None) is None


def test_normalize_rows_drops_junk_rows():
    raw = [
        {"sku": None, "model_name": "Header row", "list_price": None},
        {"sku": "ABC-1", "model_name": "Real Unit", "list_price": 999.0},
    ]
    clean = normalize_rows(raw, brand="TESTBRAND")
    assert len(clean) == 1
    assert clean[0]["SKU / Item Code"] == "ABC-1"


def test_normalize_rows_deduplicates():
    raw = [
        {"sku": "ABC-1", "model_name": "Unit", "list_price": 999.0, "source_page": 5},
        {"sku": "ABC-1", "model_name": "Unit", "list_price": 999.0, "source_page": 6},
    ]
    clean = normalize_rows(raw, brand="TESTBRAND")
    assert len(clean) == 1


def test_normalize_rows_handles_mixed_number_formats():
    raw = [
        {"sku": "EU-1", "list_price": "1.250,50", "width_mm": "600"},
        {"sku": "US-1", "list_price": "1,250.50", "width_mm": 700},
    ]
    clean = normalize_rows(raw, brand="TESTBRAND")
    assert clean[0]["List Price"] == 1250.50
    assert clean[1]["List Price"] == 1250.50
    assert clean[0]["Width (mm)"] == 600.0


def test_normalize_rows_stamps_brand_and_version():
    raw = [{"sku": "X-1", "list_price": 100}]
    clean = normalize_rows(raw, brand="ACME", price_list_version="2026")
    assert clean[0]["Brand"] == "ACME"
    assert clean[0]["Price List Version"] == "2026"


if __name__ == "__main__":
    import inspect
    test_fns = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    passed, failed = 0, 0
    for fn in test_fns:
        try:
            fn()
            passed += 1
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
