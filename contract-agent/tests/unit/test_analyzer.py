import json
import pytest
from src.analyzer import AnalyzerError, _extract_json
import json
from types import SimpleNamespace
from src.analyzer import (
    AnalyzerError,
    _extract_json,
    _validate,
    analyze_chunk,
)
from src.chunking import Chunk

def test_extract_json_accepts_plain_json():
    result = _extract_json(
        '{"clause_type": "payment", "risk_level": "low"}'
    )

    assert result == {
        "clause_type": "payment",
        "risk_level": "low",
    }


def test_extract_json_accepts_json_code_fence():
    result = _extract_json(
        """```json
        {"clause_type": "payment", "risk_level": "low"}
        ```"""
    )

    assert result["clause_type"] == "payment"
    assert result["risk_level"] == "low"


def test_extract_json_rejects_invalid_json():
    with pytest.raises(AnalyzerError, match="invalid JSON"):
        _extract_json("This is not JSON")

from src.analyzer import _validate


def valid_result() -> dict:
    return {
        "clause_type": "payment",
        "summary": "The customer must pay within 30 days.",
        "risk_level": "low",
        "risk_reason": "",
        "quoted_text": "",
    }


def test_validate_accepts_complete_result():
    data = valid_result()

    _validate(data, chunk_index=0)

    assert data["clause_type"] == "payment"


def test_validate_rejects_missing_field():
    data = valid_result()
    del data["summary"]

    with pytest.raises(AnalyzerError, match="missing fields"):
        _validate(data, chunk_index=4)


def test_validate_rejects_unknown_risk_level():
    data = valid_result()
    data["risk_level"] = "critical"

    with pytest.raises(AnalyzerError, match="invalid risk_level"):
        _validate(data, chunk_index=2)


def test_validate_converts_unknown_clause_type_to_other():
    data = valid_result()
    data["clause_type"] = "insurance"

    _validate(data, chunk_index=0)

    assert data["clause_type"] == "other"




def make_response(**overrides) -> str:
    data = {
        "clause_type": "liability",
        "summary": "The supplier has unlimited liability.",
        "risk_level": "high",
        "risk_reason": "The liability is not capped.",
        "quoted_text": "The Supplier's liability shall be unlimited.",
    }
    data.update(overrides)
    return json.dumps(data)


def test_analyze_chunk_accepts_exact_source_quote(fake_client_factory):
    chunk = Chunk(
        index=0,
        heading="5. Liability",
        text="The Supplier's liability shall be unlimited.",
    )
    client = fake_client_factory(make_response())

    verdict = analyze_chunk(chunk, client)

    assert verdict.risk_level == "high"
    assert verdict.quoted_text == (
        "The Supplier's liability shall be unlimited."
    )


def test_analyze_chunk_rejects_invented_quote(fake_client_factory):
    chunk = Chunk(
        index=0,
        heading="5. Liability",
        text="The Supplier's liability is capped at £10,000.",
    )
    client = fake_client_factory(make_response())

    with pytest.raises(
        AnalyzerError,
        match="quoted_text not found",
    ):
        analyze_chunk(chunk, client)


def test_analyze_chunk_accepts_newline_difference(fake_client_factory):
    chunk = Chunk(
        index=0,
        heading="5. Liability",
        text="The Supplier's liability\nshall be unlimited.",
    )
    client = fake_client_factory(make_response())

    verdict = analyze_chunk(chunk, client)

    assert verdict.risk_level == "high"

@pytest.mark.xfail(
    reason="Current normalization removes genuine word boundaries",
    strict=True,
)

def test_quote_guard_does_not_ignore_normal_word_boundaries(
    fake_client_factory,
):
    chunk = Chunk(
        index=0,
        heading=None,
        text="The supplier shall provide support.",
    )

    response = make_response(
        quoted_text="The suppliers hall provide support.",
    )
    client = fake_client_factory(response)

    with pytest.raises(AnalyzerError):
        analyze_chunk(chunk, client)


class BrokenLLMClient:
    def __init__(self):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=self._raise_error,
            )
        )

    @staticmethod
    def _raise_error(**kwargs):
        raise RuntimeError("Model unavailable")


def test_analyze_chunk_wraps_client_errors():
    chunk = Chunk(
        index=7,
        heading="7. Termination",
        text="Either party may terminate with 30 days' notice.",
    )

    with pytest.raises(
        AnalyzerError,
        match="Chunk 7: API call failed",
    ):
        analyze_chunk(chunk, BrokenLLMClient())

def test_analyze_chunk_sends_heading_and_text(fake_client_factory):
    chunk = Chunk(
        index=3,
        heading="3. Payment",
        text="Payment is due within 30 days.",
    )
    client = fake_client_factory(
        make_response(
            clause_type="payment",
            summary="Payment is due in 30 days.",
            risk_level="low",
            risk_reason="",
            quoted_text="",
        )
    )

    analyze_chunk(chunk, client)

    call = client.calls[0]
    user_message = call["messages"][1]["content"]

    assert "3. Payment" in user_message
    assert "Payment is due within 30 days." in user_message
    assert call["temperature"] == 0.1

def test_text_ingestion_reads_utf8_file(tmp_path):
    contract = tmp_path / "contract.txt"
    contract.write_text(
        "1. Payment\nPayment is due within 30 days.",
        encoding="utf-8",
    )

    result = ingest_document(contract)

    assert "Payment is due within 30 days." in result