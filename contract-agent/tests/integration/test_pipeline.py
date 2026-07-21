import json

import pytest

from src.pipeline import analyze_contract


@pytest.mark.integration
def test_pipeline_analyzes_text_contract(
    tmp_path,
    fake_client_factory,
):
    contract = tmp_path / "contract.txt"
    contract.write_text(
        "1. Payment\nPayment shall be made within 30 days.",
        encoding="utf-8",
    )

    response = json.dumps(
        {
            "clause_type": "payment",
            "summary": "Payment is due within 30 days.",
            "risk_level": "low",
            "risk_reason": "",
            "quoted_text": "",
        }
    )
    client = fake_client_factory(response)

    report = analyze_contract(
        str(contract),
        client=client,
    )

    assert len(report.verdicts) == 1
    assert report.verdicts[0].clause_type == "payment"
    assert report.failed_chunk_indices == []