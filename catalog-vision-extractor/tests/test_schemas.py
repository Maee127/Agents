"""Tests for the pydantic validation models."""
import pytest
from pydantic import ValidationError

from src.schemas import PageClassification, RawProductRow


class TestPageClassification:
    def test_valid(self):
        pc = PageClassification.model_validate({"page_type": "price_table", "confidence": 0.92})
        assert pc.page_type == "price_table"
        assert pc.confidence == 0.92

    def test_invalid_page_type(self):
        with pytest.raises(ValidationError):
            PageClassification.model_validate({"page_type": "recipe", "confidence": 0.9})

    @pytest.mark.parametrize("confidence", [-0.1, 1.5])
    def test_confidence_bounds(self, confidence):
        with pytest.raises(ValidationError):
            PageClassification.model_validate({"page_type": "spec", "confidence": confidence})


class TestRawProductRow:
    def test_sparse_row_is_valid(self):
        row = RawProductRow.model_validate({"sku": "AC-1"})
        assert row.sku == "AC-1"
        assert row.list_price is None

    def test_messy_string_numbers_accepted(self):
        row = RawProductRow.model_validate({"sku": "AC-1", "list_price": "1.250,50"})
        assert row.list_price == "1.250,50"

    def test_numeric_sku_coerced_to_string(self):
        row = RawProductRow.model_validate({"sku": 40101, "model_name": "X"})
        assert row.sku == "40101"

    def test_extra_keys_ignored(self):
        row = RawProductRow.model_validate({"sku": "AC-1", "made_up_field": "x"})
        assert not hasattr(row, "made_up_field")

    def test_non_object_rejected(self):
        with pytest.raises(ValidationError):
            RawProductRow.model_validate("just a string")
