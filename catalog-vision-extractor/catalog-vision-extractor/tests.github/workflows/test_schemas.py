import pytest

from pydantic import ValidationError

from src.schemas import ExtractedRow, PageClassification, Dimensions


def test_valid_extracted_row():
    sample = {
        "brand": "ACME",
        "sku": "AC-123",
        "model_name": "Cooler 3000",
        "product_family": "Coolers",
        "product_category": "Refrigeration",
        "dimensions": {"width_mm": 800.0, "depth_mm": 700.0, "height_mm": 1800.0},
        "list_price": 12345.67,
        "currency": "EUR",
        "price_list_version": "2026",
        "source_page": 5,
        "notes": "Imported from ACME 2026 PDF",
        "raw": {"some": "raw data"},
    }

    row = ExtractedRow.model_validate(sample)

    assert row.brand == "ACME"
    assert row.sku == "AC-123"
    assert row.model_name == "Cooler 3000"
    assert row.list_price == 12345.67
    assert row.currency == "EUR"
    assert row.source_page == 5
    assert isinstance(row.dimensions, Dimensions)


def test_negative_price_fails():
    sample = {"brand": "ACME", "sku": "AC-1", "model_name": "X", "list_price": -1}
    with pytest.raises(ValidationError):
        ExtractedRow.model_validate(sample)


def test_classification_model():
    c = {"page_type": "price_table", "confidence": 0.92, "page_number": 3}
    pc = PageClassification.model_validate(c)
    assert pc.page_type == "price_table"
    assert 0.0 <= pc.confidence <= 1.0
    assert pc.page_number == 3


def test_invalid_classification_confidence():
    c = {"page_type": "spec", "confidence": 1.5, "page_number": 1}
    with pytest.raises(ValidationError):
        PageClassification.model_validate(c)
