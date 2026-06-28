"""
Pipeline orchestrator + CLI entry point.

Usage:
    python -m src.pipeline --pdf data/input/acme_2026.pdf --brand ACME
    python -m src.pipeline --pdf data/input/acme_2026.pdf --brand ACME --version 2026
    python -m src.pipeline --all
    python -m src.pipeline --pdf data/input/acme_2026.pdf --brand ACME --no-cache
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.cache import cache_stats
from src.classifier import classify_pages
from src.config import INPUT_DIR, MASTER_EXCEL_PATH, TARGET_PAGE_TYPE, validate_config
from src.exporter import write_master_excel
from src.extractor import extract_pages
from src.normalizer import normalize_rows
from src.rasterizer import rasterize_pdf


def run_pipeline(
    pdf_path: Path,
    brand: str,
    price_list_version: str = "",
    use_cache: bool = True,
) -> dict:
    """
    Run the full pipeline on one brand PDF and merge results into the master
    Excel file. Returns a small summary dict for CLI reporting.
    """
    t0 = time.time()
    print(f"\n=== {brand} :: {pdf_path.name} ===")

    print("[1/5] rasterizing PDF to page images...")
    pages = rasterize_pdf(pdf_path)
    print(f"      {len(pages)} page(s) rendered")

    print("[2/5] classifying pages...")
    classifications = classify_pages(pages, use_cache=use_cache)
    type_counts: dict[str, int] = {}
    for c in classifications:
        type_counts[c["page_type"]] = type_counts.get(c["page_type"], 0) + 1
    print(f"      breakdown: {type_counts}")

    target_page_numbers = {
        c["page_number"] for c in classifications if c["page_type"] == TARGET_PAGE_TYPE
    }
    target_pages = [p for p in pages if p.page_number in target_page_numbers]
    print(f"      {len(target_pages)} page(s) classified as '{TARGET_PAGE_TYPE}' -> extracting")

    print("[3/5] extracting structured data from price table pages...")
    raw_rows = extract_pages(target_pages, use_cache=use_cache)
    print(f"      {len(raw_rows)} raw row(s) extracted")

    print("[4/5] normalizing...")
    clean_rows = normalize_rows(
        raw_rows, brand=brand, price_list_version=price_list_version
    )
    print(f"      {len(clean_rows)} clean row(s) after dedup/validation")

    print("[5/5] writing to master Excel...")
    output_path = write_master_excel(clean_rows, brand=brand, price_list_version=price_list_version)
    print(f"      -> {output_path}")

    elapsed = time.time() - t0
    print(f"done in {elapsed:.1f}s")

    return {
        "brand": brand,
        "pages_total": len(pages),
        "pages_extracted": len(target_pages),
        "rows_raw": len(raw_rows),
        "rows_clean": len(clean_rows),
        "elapsed_seconds": round(elapsed, 1),
    }


def _brand_from_filename(pdf_path: Path) -> str:
    """Fallback brand name guess if --brand isn't given: filename without extension/version suffix."""
    stem = pdf_path.stem
    return stem.split("_")[0].upper()


def main() -> None:
    parser = argparse.ArgumentParser(description="Catalog Vision Extractor pipeline")
    parser.add_argument("--pdf", type=Path, help="Path to a single brand PDF to process")
    parser.add_argument("--brand", type=str, help="Brand name to stamp on extracted rows")
    parser.add_argument("--version", type=str, default="", help="Price list version label, e.g. '2026'")
    parser.add_argument("--all", action="store_true", help="Process every PDF in data/input/")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached classify/extract results")
    args = parser.parse_args()

    validate_config()
    use_cache = not args.no_cache

    if args.all:
        pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
        if not pdf_paths:
            print(f"No PDFs found in {INPUT_DIR}")
            sys.exit(1)
        summaries = [
            run_pipeline(p, brand=_brand_from_filename(p), price_list_version=args.version, use_cache=use_cache)
            for p in pdf_paths
        ]
    elif args.pdf:
        if not args.brand:
            print("Error: --brand is required when using --pdf")
            sys.exit(1)
        summaries = [
            run_pipeline(args.pdf, brand=args.brand, price_list_version=args.version, use_cache=use_cache)
        ]
    else:
        parser.print_help()
        sys.exit(1)

    print("\n=== summary ===")
    for s in summaries:
        print(s)
    print(f"\nclassification cache: {cache_stats('classify')}")
    print(f"extraction cache:     {cache_stats('extract')}")
    print(f"\nmaster file: {MASTER_EXCEL_PATH}")


if __name__ == "__main__":
    main()
