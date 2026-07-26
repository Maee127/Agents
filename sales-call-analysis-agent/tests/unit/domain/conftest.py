"""Fixtures providing valid, obviously synthetic domain-model constructor kwargs."""

from datetime import UTC, datetime
from typing import Any

import pytest

from sales_call_agent.domain import AudioChannels, SourceType

SYNTHETIC_SELLER_NUMBER = "+15550000001"
SYNTHETIC_COUNTERPARTY_PHONE = "+15550000002"


@pytest.fixture
def metadata_kwargs() -> dict[str, Any]:
    """Valid kwargs for ``CallMetadata`` using synthetic (555) phone numbers."""
    return {
        "call_id": "call-0001",
        "seller_number": SYNTHETIC_SELLER_NUMBER,
        "source_type": SourceType.RECORDER_APP,
        "call_timestamp": datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
        "duration_seconds": 182.5,
        "counterparty_phone": SYNTHETIC_COUNTERPARTY_PHONE,
        "original_filename": "+15550000002_20260726_093000.mp3",
        "audio_channels": AudioChannels.MONO,
        "storage_path": "calls/seller-0001/2026-07-26/call-0001.mp3",
    }


@pytest.fixture
def audio_kwargs() -> dict[str, Any]:
    """Valid kwargs for ``AudioAsset``, consistent with ``metadata_kwargs``."""
    return {
        "storage_path": "calls/seller-0001/2026-07-26/call-0001.mp3",
        "audio_channels": AudioChannels.MONO,
        "content_hash": "9f2c" * 16,
    }
