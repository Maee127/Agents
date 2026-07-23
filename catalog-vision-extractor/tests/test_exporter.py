"""Tests for the Excel exporter, especially the brand+version replace behavior."""
import pandas as pd

from src.config import MASTER_COLUMNS
from src.exporter import write_master_excel


def _row(brand: str, sku: str, price: float, version: str = "") -> dict:
    row = {col: None for col in MASTER_COLUMNS}
    row["Brand"] = brand
    row["SKU / Item Code"] = sku
    row["List Price"] = price
    row["Price List Version"] = version
    row["Notes"] = ""
    return row


def _read(path) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name="Master", dtype=object)


def test_creates_file_with_master_columns(tmp_path):
    path = tmp_path / "master.xlsx"
    write_master_excel([_row("ACME", "A-1", 100.0)], "ACME", "", path=path)
    df = _read(path)
    assert list(df.columns) == MASTER_COLUMNS
    assert len(df) == 1


def test_other_brands_are_preserved(tmp_path):
    path = tmp_path / "master.xlsx"
    write_master_excel([_row("ACME", "A-1", 100.0)], "ACME", "", path=path)
    write_master_excel([_row("OTHER", "O-1", 50.0)], "OTHER", "", path=path)
    df = _read(path)
    assert set(df["Brand"]) == {"ACME", "OTHER"}
    assert len(df) == 2


def test_rerun_replaces_same_brand_and_version(tmp_path):
    path = tmp_path / "master.xlsx"
    write_master_excel([_row("ACME", "A-1", 100.0, "2026")], "ACME", "2026", path=path)
    write_master_excel([_row("ACME", "A-2", 200.0, "2026")], "ACME", "2026", path=path)
    df = _read(path)
    assert len(df) == 1
    assert df.iloc[0]["SKU / Item Code"] == "A-2"


def test_rerun_with_empty_version_replaces_not_duplicates(tmp_path):
    """Regression test: empty version round-trips through Excel as NaN, which
    used to break the == "" comparison and duplicate rows on every re-run."""
    path = tmp_path / "master.xlsx"
    write_master_excel([_row("ACME", "A-1", 100.0)], "ACME", "", path=path)
    write_master_excel([_row("ACME", "A-1", 100.0)], "ACME", "", path=path)
    df = _read(path)
    assert len(df) == 1


def test_different_versions_of_same_brand_coexist(tmp_path):
    path = tmp_path / "master.xlsx"
    write_master_excel([_row("ACME", "A-1", 100.0, "2025")], "ACME", "2025", path=path)
    write_master_excel([_row("ACME", "A-1", 110.0, "2026")], "ACME", "2026", path=path)
    df = _read(path)
    assert len(df) == 2


def test_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "master.xlsx"
    write_master_excel([_row("ACME", "A-1", 100.0)], "ACME", "", path=path)
    leftovers = [p for p in tmp_path.iterdir() if p.name != "master.xlsx"]
    assert leftovers == []
