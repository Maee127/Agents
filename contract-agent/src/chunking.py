"""
Chunking: split extracted contract text into clause-sized pieces.

Strategy (two stages):
  1. Regex structural split -- find numbered/lettered headers
     ("1.", "2.1", "Section 3:", "ARTICLE IV") and split there.
     This gives chunks that map to real clauses, which matters later
     for explaining results to a client ("clause 4.2 is risky") and
     for comparing clauses across documents in the memory feature.
  2. Sentence-boundary safety net -- applied only to chunks the regex
     pass produced that are still too large (meaning the numbering
     heuristic likely missed something). Splits on sentence
     boundaries so a chunk is never cut mid-sentence, unlike a naive
     fixed-character-length split.
"""

import re
from dataclasses import dataclass

# Matches common contract header styles at the start of a line:
#   "1.", "2.1", "12)", "Section 3:", "Section 3.1", "ARTICLE IV"
# This is deliberately permissive -- false positives (treating a non-header
# line as a header) are cheaper than false negatives here, because a wrongly
# split header just creates one extra small chunk, while a missed header
# risks merging unrelated clauses together.
HEADER_PATTERN = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*[.)]\s+"          # 1.  /  2.1.  /  3)
    r"|[A-Z]\.\s+"                    # A.  /  B.
    r"|Section\s+\d+(?:\.\d+)*:?\s*"  # Section 3:  /  Section 3.1
    r"|ARTICLE\s+[IVXLCDM]+\b"        # ARTICLE IV
    r")",
    re.MULTILINE,
)

# If a chunk produced by the regex pass exceeds this, it's a sign the
# numbering heuristic missed a header somewhere inside it -- the
# sentence-boundary fallback then re-splits it.
MAX_CHUNK_CHARS = 1200

# Simple sentence boundary: a period/!/? followed by whitespace and a
# capital letter or end of text. Not linguistically perfect (struggles
# with abbreviations like "U.S." or "Inc."), which is fine here -- the
# fallback only needs to avoid mid-sentence cuts, not parse grammar.
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


@dataclass
class Chunk:
    index: int
    heading: str | None  # e.g. "1." or "Section 3:" -- None if from fallback
    text: str


def chunk_document(text: str) -> list[Chunk]:
    structural_chunks = _split_on_headers(text)

    final_chunks: list[str] = []
    final_headings: list[str | None] = []

    for heading, body in structural_chunks:
        if len(body) <= MAX_CHUNK_CHARS:
            final_chunks.append(body)
            final_headings.append(heading)
        else:
            # Heuristic likely missed a header inside this block --
            # fall back to sentence-safe splitting.
            for piece in _split_by_sentences(body, MAX_CHUNK_CHARS):
                final_chunks.append(piece)
                final_headings.append(heading)  # keep parent heading for context

    return [
        Chunk(index=i, heading=h, text=t.strip())
        for i, (h, t) in enumerate(zip(final_headings, final_chunks))
        if t.strip()
    ]


def _split_on_headers(text: str) -> list[tuple[str | None, str]]:
    """
    Returns list of (heading_text_or_None, body_text) tuples.
    If no headers are found at all, returns the whole text as one
    chunk with heading=None, which will then go through the sentence
    fallback in chunk_document if it's too long.
    """
    matches = list(HEADER_PATTERN.finditer(text))

    if not matches:
        return [(None, text)]

    results = []
    for i, match in enumerate(matches):
        heading = match.group().strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            results.append((heading, body))

    # Capture any preamble text before the first detected header
    # (e.g. a title line like "SERVICE AGREEMENT").
    preamble = text[: matches[0].start()].strip()
    if preamble:
        results.insert(0, (None, preamble))

    return results


def _split_by_sentences(text: str, max_chars: int) -> list[str]:
    """Greedily pack sentences into pieces, never exceeding max_chars,
    and never splitting a sentence itself."""
    sentences = SENTENCE_BOUNDARY.split(text)

    pieces = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)

    return pieces