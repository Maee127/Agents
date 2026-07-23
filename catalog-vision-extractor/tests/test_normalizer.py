"""Tests for the normalizer — the module with the most real-world-messiness logic."""
import pytest

from src.normalizer import _clean_number, _clean_text, normalize_rows


class TestCleanNumber:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Already numeric
            (1250, 1250.0),
            (1250.5, 1250.5),
            # Plain strings
            ("1250", 1250.0),
            ("1250.5", 1250.5),
            # EU format: period thousands, comma decimal
            ("1.250,50", 1250.50),
            ("1.250.000,99", 1250000.99),
            ("210,5", 210.5),
            # US format: comma thousands, period decimal
            ("1,250.50", 1250.50),
            ("8,450", 8450.0),
            ("1,000,000", 1000000.0),
            # Currency symbols and stray text
            ("EUR 1250,50", 1250.50),
            ("$1,250.50", 1250.50),
            ("1.250,50 \u20ac", 1250.50),
            # Negatives
            ("-45.5", -45.5),
            ("-1.250,50", -1250.50),
        ],
    )
    def test_formats(self, raw, expected):
        assert _clean_number(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "n/a", "---", "abc"])
    def test_unparseable_returns_none(self, raw):
        assert _clean_number(raw) is None


class TestCleanText:
    def test_collapses_multiline_names(self):
        assert _clean_text("Combi\nOven\n  60") == "Combi Oven 60"

    def test_none_and_empty(self):
        assert _clean_text(None) is None
        assert _clean_text("   ") is None


class TestNormalizeRows:
    def _raw_row(self, **overrides):
        row = {
            "sku": "AB-100",
            "model_name": "Unit 100",
            "list_price": "1.250,50",
            "source_page": 7,
        }
        row.update(overrides)
        return row

    def test_maps_and_cleans(self):
        rows = normalize_rows([self._raw_row()], brand="ACME", price_list_version="2026")
        assert len(rows) == 1
        row = rows[0]
        assert row["Brand"] == "ACME"
        assert row["SKU / Item Code"] == "AB-100"
        assert row["List Price"] == 1250.50
        assert row["Price List Version"] == "2026"
        assert row["Source Page"] == 7
        assert row["Notes"] == ""

    def test_drops_rows_without_sku_and_price(self):
        junk = self._raw_row(sku=None, list_price=None)
        rows = normalize_rows([junk], brand="ACME")
        assert rows == []

    def test_keeps_row_with_price_but_no_sku(self):
        rows = normalize_rows([self._raw_row(sku=None)], brand="ACME")
        assert len(rows) == 1

    def test_deduplicates_same_sku_and_price(self):
        duplicates = [self._raw_row(), self._raw_row(source_page=8)]
        rows = normalize_rows(duplicates, brand="ACME")
        assert len(rows) == 1

    def test_same_sku_different_price_kept(self):
        variants = [self._raw_row(), self._raw_row(list_price="999")]
        rows = normalize_rows(variants, brand="ACME")
        assert len(rows) == 2
