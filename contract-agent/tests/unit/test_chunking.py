from src.chunking import MAX_CHUNK_CHARS, chunk_document
import json

def test_chunk_document_splits_numbered_sections():
    text = """
1. Payment
The customer shall pay within 30 days.

2. Termination
Either party may terminate on written notice.
"""

    chunks = chunk_document(text)

    assert len(chunks) == 2
    assert chunks[0].heading == "1."
    assert "customer shall pay" in chunks[0].text
    assert chunks[1].heading == "2."
    assert "Either party may terminate" in chunks[1].text


def test_chunk_document_splits_section_headings():
    text = """
Section 1: Services
The supplier will provide hosting.

Section 2: Fees
The customer will pay monthly.
"""

    chunks = chunk_document(text)

    assert len(chunks) == 2
    assert chunks[0].heading.startswith("Section 1")
    assert chunks[1].heading.startswith("Section 2")


def test_chunk_document_splits_article_heading():
    text = """
ARTICLE I
GENERAL TERMS

ARTICLE II
PAYMENT TERMS
"""

    chunks = chunk_document(text)

    assert len(chunks) == 2
    assert chunks[0].heading.startswith("ARTICLE I")
    assert chunks[1].heading.startswith("ARTICLE II")


def test_chunk_indices_are_sequential():
    text = """
1. First
First clause.

2. Second
Second clause.
"""

    chunks = chunk_document(text)

    assert [chunk.index for chunk in chunks] == [0, 1]


def test_empty_text_produces_no_chunks():
    assert chunk_document("") == []


def test_long_text_with_sentence_boundaries_is_split():
    sentence = "The supplier shall provide the service. "
    text = sentence * 100

    chunks = chunk_document(text)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)

def test_inline_article_heading_is_detected():
    text = (
        "The initial provisions apply. "
        "ARTICLE 2. PAYMENT TERMS "
        "Payment is due within 30 days."
    )

    chunks = chunk_document(text)

    assert len(chunks) == 2
    assert chunks[0].heading is None
    assert chunks[0].text == "The initial provisions apply."
    assert chunks[1].heading == "ARTICLE 2."
    assert "PAYMENT TERMS" in chunks[1].text

