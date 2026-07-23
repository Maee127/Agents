"""Tests for the classifier/extractor response parsing — no API calls needed."""
import pytest

from src.classifier import _parse_classification
from src.extractor import _parse_extraction


class TestParseClassification:
    def test_clean_json(self):
        result = _parse_classification('{"page_type": "price_table", "confidence": 0.95}')
        assert result == {"page_type": "price_table", "confidence": 0.95}

    def test_tolerates_surrounding_text_and_fences(self):
        raw = 'Sure! Here it is:\n```json\n{"page_type": "intro", "confidence": 0.8}\n```'
        result = _parse_classification(raw)
        assert result["page_type"] == "intro"

    def test_unknown_page_type_rejected(self):
        with pytest.raises(ValueError):
            _parse_classification('{"page_type": "banana", "confidence": 0.9}')

    def test_out_of_range_confidence_rejected(self):
        with pytest.raises(ValueError):
            _parse_classification('{"page_type": "spec", "confidence": 1.5}')

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            _parse_classification("I cannot classify this page.")


class TestParseExtraction:
    def test_clean_array(self):
        rows = _parse_extraction('[{"sku": "A-1", "model_name": "X", "list_price": 100}]')
        assert len(rows) == 1
        assert rows[0]["sku"] == "A-1"
        assert rows[0]["list_price"] == 100

    def test_strips_code_fences(self):
        raw = '```json\n[{"sku": "A-1", "model_name": "X"}]\n```'
        rows = _parse_extraction(raw)
        assert rows[0]["sku"] == "A-1"

    def test_messy_string_numbers_pass_through(self):
        # Raw values may be locale-formatted strings; cleaning is the
        # normalizer's job, so parsing must not reject them.
        rows = _parse_extraction('[{"sku": "A-1", "model_name": "X", "list_price": "1.250,50"}]')
        assert rows[0]["list_price"] == "1.250,50"

    def test_structurally_invalid_rows_dropped(self):
        raw = '[{"sku": "A-1", "model_name": "X"}, "not an object", 42]'
        rows = _parse_extraction(raw)
        assert len(rows) == 1

    def test_unknown_keys_ignored(self):
        rows = _parse_extraction('[{"sku": "A-1", "model_name": "X", "hallucinated": true}]')
        assert "hallucinated" not in rows[0]

    def test_no_array_raises(self):
        with pytest.raises(ValueError):
            _parse_extraction("There is no price table on this page.")

    def test_non_list_json_raises(self):
        with pytest.raises(ValueError):
            _parse_extraction('{"sku": "A-1"}')
