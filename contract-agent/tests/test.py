# # tests/test.py
# import sys, os

# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# SRC_DIR = os.path.join(SCRIPT_DIR, "..", "src")
# sys.path.insert(0, SRC_DIR)

# from ingestion import ingest_document, IngestionError
# from chunking import chunk_document

# OUTPUT_DIR = os.path.join(SCRIPT_DIR, "test_run_1")
# os.makedirs(OUTPUT_DIR, exist_ok=True)

# SAMPLES_DIR = os.path.join(SCRIPT_DIR, "sample_contracts")

# # Process every PDF in the samples folder, not just one
# for file_name in os.listdir(SAMPLES_DIR):
#     if not file_name.lower().endswith(".pdf"):
#         continue

#     file_path = os.path.join(SAMPLES_DIR, file_name)

#     try:
#         text = ingest_document(file_path)
#         chunks = chunk_document(text)

#         out_path = os.path.join(OUTPUT_DIR, f"{file_name}.chunks.txt")
#         with open(out_path, "w", encoding="utf-8") as f:
#             f.write(f"Source: {file_path}\n")
#             f.write(f"Total chunks: {len(chunks)}\n\n")
#             for c in chunks:
#                 f.write(f"[{c.index}] heading={c.heading!r}\n")
#                 f.write(f"{c.text}\n")
#                 f.write("-" * 60 + "\n")

#         print(f"[OK] {file_name} -> {len(chunks)} chunks saved to {out_path}")

#     except IngestionError as e:
#         print(f"[FAILED] {file_name}: {type(e).__name__}: {e}")
# tests/test.py
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, "..", "src")
sys.path.insert(0, SRC_DIR)

import anthropic
from ingestion import ingest_document, IngestionError
from chunking import chunk_document
from analyzer import analyze_chunk, AnalyzerError

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "test_run_2")  # new folder, so test_run_1 stays as a record
os.makedirs(OUTPUT_DIR, exist_ok=True)

SAMPLES_DIR = os.path.join(SCRIPT_DIR, "sample_contracts")

# Only run the analyzer on the 3 confirmed-real contracts, to avoid
# wasting API calls on Contract-1/4 which aren't actual contracts.
TARGET_FILES = ["Contract-2.pdf", "Contract-3.pdf", "Contract-5.pdf"]

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from your environment

for file_name in TARGET_FILES:
    file_path = os.path.join(SAMPLES_DIR, file_name)

    try:
        text = ingest_document(file_path)
        chunks = chunk_document(text)
    except IngestionError as e:
        print(f"[FAILED] {file_name}: {type(e).__name__}: {e}")
        continue

    out_path = os.path.join(OUTPUT_DIR, f"{file_name}.verdicts.txt")
    failed_count = 0

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Source: {file_path}\n")
        f.write(f"Total chunks: {len(chunks)}\n\n")

        for chunk in chunks:
            try:
                verdict = analyze_chunk(chunk, client)
                f.write(f"[{verdict.chunk_index}] heading={verdict.heading!r}\n")
                f.write(f"  clause_type: {verdict.clause_type}\n")
                f.write(f"  summary:     {verdict.summary}\n")
                f.write(f"  risk_level:  {verdict.risk_level}\n")
                if verdict.risk_level != "low":
                    f.write(f"  risk_reason: {verdict.risk_reason}\n")
                    f.write(f"  quoted:      {verdict.quoted_text!r}\n")
                f.write("-" * 60 + "\n")
            except AnalyzerError as e:
                failed_count += 1
                f.write(f"[{chunk.index}] ANALYZER ERROR: {e}\n")
                f.write("-" * 60 + "\n")

    print(f"[OK] {file_name} -> {len(chunks)} chunks analyzed "
          f"({failed_count} failed) -> {out_path}")
    