# Master Excel schema reference

Every brand's extracted data lands in the same `Master` sheet using this exact
column order. `normalizer.py`'s `MASTER_COLUMNS` (in `src/config.py`) is the
single source of truth — this doc is just a human-readable mirror of it.

| Column | Type | Notes |
|---|---|---|
| Brand | text | Stamped from the `--brand` CLI argument, not extracted from the page |
| SKU / Item Code | text | Primary product identifier; rows without one (and without a price) are dropped as junk |
| Model Name | text | Multi-line names are collapsed to a single line |
| Product Family / Series | text | Not auto-populated by the current extraction prompt — left as a manual enrichment column for now |
| Product Category | text | e.g. "Oven", "Refrigeration" — populated only if visible on the price table page itself |
| Width (mm) | number | |
| Depth (mm) | number | |
| Height (mm) | number | |
| Net Weight (kg) | number | |
| Gross Weight (kg) | number | |
| Volume (L) | number | |
| Power Supply (V/Hz) | text | Kept as written, e.g. "400V/50Hz/3N" — not split into separate V/Hz columns |
| Power Consumption (W) | number | |
| Refrigerant Gas | text | e.g. "R290" |
| Energy Class | text | e.g. "A+" |
| Temperature Range (C) | text | Kept as written, e.g. "-18/+3" — ranges aren't split into min/max columns |
| List Price | number | Cleaned of currency symbols and thousands separators; EU (1.250,50) and US (1,250.50) formats are both handled |
| Currency | text | Symbol or ISO code as shown on the page |
| Price List Version | text | Free-text label passed via `--version`, e.g. "2026" |
| Price List Date | date (ISO) | Defaults to the date the pipeline was run if not specified |
| Source Page | number | 1-indexed page number in the source PDF — for tracing a row back to verify it |
| Notes | text | Empty by default; reserved for manual QA flags |

## Re-run / update behavior

Running the pipeline again with the same `--brand` and `--version` **replaces**
that brand+version's existing rows in the master file rather than duplicating
them. Other brands and other versions of the same brand are untouched. This is
what lets you re-run the pipeline every year when a brand ships a new
catalogue without manually cleaning up the old data first.
