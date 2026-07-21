from src.ingestion import ingest_document


def test_text_ingestion_reads_utf8_file(tmp_path):
    contract = tmp_path / "contract.txt"
    contract.write_text(
        "1. Payment\nPayment is due within 30 days.",
        encoding="utf-8",
    )

    result = ingest_document(str(contract))

    assert "Payment is due within 30 days." in result