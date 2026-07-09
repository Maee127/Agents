# tests/test.py
import sys, os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, "..", "src")
sys.path.insert(0, SRC_DIR)

from ingestion import ingest_document, IngestionError
from chunking import chunk_document
from analyzer import analyze_chunk, AnalyzerError
from local_llm import LocalLLMClient
from dotenv import load_dotenv


load_dotenv(os.path.join(SCRIPT_DIR, "..", ".env"))

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "test_run_2")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SAMPLES_DIR = os.path.join(SCRIPT_DIR, "sample_contracts")
TARGET_FILES = ["Contract-2.pdf", "Contract-3.pdf", "Contract-5.pdf"]

client = LocalLLMClient()

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
    
    print(f"\n[START] Processing {file_name} ({len(chunks)} chunks)")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Source: {file_path}\n")
        f.write(f"Total chunks: {len(chunks)}\n\n")

        for i, chunk in enumerate(chunks):
            # FIX 2: Add progress logging to see which chunk is slow
            chunk_heading = chunk.heading or "(no heading)"
            print(f"  [{i+1}/{len(chunks)}] {chunk_heading}...", end=" ", flush=True)
            chunk_start = time.time()
            
            try:
                verdict = analyze_chunk(chunk, client)
                chunk_elapsed = time.time() - chunk_start
                print(f"✓ ({chunk_elapsed:.1f}s)")
                
                f.write(f"[{verdict.chunk_index}] heading={verdict.heading!r}\n")
                f.write(f"  clause_type: {verdict.clause_type}\n")
                f.write(f"  summary:     {verdict.summary}\n")
                f.write(f"  risk_level:  {verdict.risk_level}\n")
                if verdict.risk_level != "low":
                    f.write(f"  risk_reason: {verdict.risk_reason}\n")
                    f.write(f"  quoted:      {verdict.quoted_text!r}\n")
                f.write("-" * 60 + "\n")
            except AnalyzerError as e:
                chunk_elapsed = time.time() - chunk_start
                print(f"✗ ERROR ({chunk_elapsed:.1f}s)")
                failed_count += 1
                f.write(f"[{chunk.index}] ANALYZER ERROR: {e}\n")
                f.write("-" * 60 + "\n")

    print(f"[OK] {file_name} -> {len(chunks)} chunks, "
          f"{failed_count} failed -> {out_path}\n")
