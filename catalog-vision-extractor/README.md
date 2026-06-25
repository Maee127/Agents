# Catalog Vision Extractor

Turn messy, multi-brand commercial-equipment PDF price catalogues into one clean,
structured Excel database — using a vision LLM instead of brittle text parsing.

## The problem

Commercial equipment distributors get an annual PDF price list from every brand
they carry. These PDFs are professionally designed catalogues (usually exported
from Adobe InDesign) that mix:

- full-bleed marketing/intro pages
- multilingual product description pages
- technical drawing pages with dimensions
- price table pages — the only pages that actually matter

Layouts vary wildly between brands, so a traditional PDF text parser (pdfplumber,
camelot, etc.) breaks constantly: it can't tell a price table from a spec sheet,
and it can't reliably find which column is "list price" vs "weight" when every
brand lays the table out differently.

## The approach

1. **Rasterize** — render every PDF page to a PNG image.
2. **Classify** — send each page image to a vision LLM and ask it to label the
   page as `intro`, `spec`, `drawing`, or `price_table`. Only `price_table`
   pages move forward.
3. **Extract** — send each `price_table` page image to the vision LLM again,
   this time asking for structured JSON: SKU, model name, dimensions, weight,
   power spec, energy class, list price, etc.
4. **Normalize** — clean the raw JSON: standardize units, fix multi-line model
   names, drop duplicate header rows, validate that price fields are numeric.
5. **Export** — write everything into one Master Excel file with a fixed
   column schema across all brands.

The pipeline is **idempotent per page** — each page image is hashed, and results
are cached against that hash. Re-running on an updated PDF only reprocesses
pages that actually changed, which is what makes it practical to re-run every
year when a brand ships a new catalogue.

## Project structure

```
catalog-vision-extractor/
├── src/
│   ├── config.py        # model selection, API keys, paths
│   ├── rasterizer.py     # PDF -> page images
│   ├── classifier.py      # page image -> page type
│   ├── extractor.py        # price_table image -> structured JSON
│   ├── normalizer.py        # raw JSON -> clean rows
│   ├── exporter.py            # clean rows -> Master Excel
│   ├── cache.py                 # page-hash -> cached result
│   └── pipeline.py                # ties it all together + CLI
├── data/
│   ├── input/             # put brand PDFs here
│   ├── cache/              # cached per-page classification/extraction results
│   └── output/              # Master Excel file ends up here
├── tests/                  # sample fixtures + unit tests
└── docs/                     # extra docs (schema reference, runbook)
```

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then fill in your API key
```

You need an API key from **one** of:
- Anthropic (`ANTHROPIC_API_KEY`) — recommended, cheapest is `claude-haiku-4-5`
- OpenAI (`OPENAI_API_KEY`) — `gpt-4o-mini` is the cheap vision option

Both providers bill per token — there is no free production tier — but a
single brand's price-table pages (typically 10-30 pages) costs a few cents
to process even with caching disabled.

## Usage

```bash
# Run the full pipeline on one brand PDF
python -m src.pipeline --pdf data/input/acme_2026.pdf --brand ACME

# Re-run after the brand sends an updated catalogue — only changed
# pages get reprocessed, thanks to the page-hash cache
python -m src.pipeline --pdf data/input/acme_2026_v2.pdf --brand ACME

# Process every PDF in data/input/ in one go
python -m src.pipeline --all

# Force a clean re-extraction, ignoring the cache
python -m src.pipeline --pdf data/input/acme_2026.pdf --brand ACME --no-cache
```

Output lands in `data/output/master_pricelist.xlsx`. Running the pipeline again
on a different brand appends to the same master file rather than overwriting it.

## Master Excel schema

See [`docs/schema.md`](docs/schema.md) for the full column reference.

## Known limitations (and why they're there)

This is a portfolio-scale build, so a few things are deliberately out of scope:

- **Multilingual spec pages are classified and skipped, not translated.** The
  full job spec asks for 4-language support; this POC proves the
  classification/extraction mechanism on the language that matters most
  (the price table itself, which is usually numbers + a SKU code, not prose).
- **No OCR fallback.** If a PDF page is a scanned image with no embedded text
  layer, the vision model still works (it reads pixels either way) but
  extraction accuracy may dip on low-resolution scans.
- **Single quotation currency per brand.** Multi-currency catalogues would need
  a currency-detection step per row.

## License

MIT
