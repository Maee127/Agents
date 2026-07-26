"""Behavioral tests for CallMetadata invariants and privacy guarantees."""

from datetime import datetime, timedelta, tzinfo
from typing import Any

import pytest

from sales_call_agent.domain import (
    AudioChannels,
    CallMetadata,
    InvalidCallMetadataError,
    SourceType,
)


class _IneffectiveTzinfo(tzinfo):
    """A tzinfo whose utcoffset is None, making the datetime effectively naive."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None


def test_constructs_with_all_valid_fields(metadata_kwargs: dict[str, Any]) -> None:
    metadata = CallMetadata(**metadata_kwargs)

    assert metadata.call_id == "call-0001"
    assert metadata.source_type is SourceType.RECORDER_APP
    assert metadata.audio_channels is AudioChannels.MONO
    assert metadata.duration_seconds == 182.5


def test_counterparty_phone_may_be_none(metadata_kwargs: dict[str, Any]) -> None:
    metadata_kwargs["counterparty_phone"] = None

    assert CallMetadata(**metadata_kwargs).counterparty_phone is None


@pytest.mark.parametrize(
    "field_name", ["call_id", "seller_number", "original_filename", "storage_path"]
)
@pytest.mark.parametrize("bad_value", ["", "   ", None, 123, b"raw-bytes"])
def test_rejects_invalid_required_strings(
    metadata_kwargs: dict[str, Any], field_name: str, bad_value: object
) -> None:
    metadata_kwargs[field_name] = bad_value

    with pytest.raises(InvalidCallMetadataError, match=field_name):
        CallMetadata(**metadata_kwargs)


def test_preserves_original_string_values_without_normalizing(
    metadata_kwargs: dict[str, Any],
) -> None:
    metadata_kwargs["call_id"] = "  call-0001  "

    assert CallMetadata(**metadata_kwargs).call_id == "  call-0001  "


@pytest.mark.parametrize("bad_value", ["", "   ", 42])
def test_rejects_invalid_counterparty_phone(
    metadata_kwargs: dict[str, Any], bad_value: object
) -> None:
    metadata_kwargs["counterparty_phone"] = bad_value

    with pytest.raises(InvalidCallMetadataError, match="counterparty_phone"):
        CallMetadata(**metadata_kwargs)


@pytest.mark.parametrize(
    ("field_name", "raw_value"),
    [("source_type", "recorder_app"), ("audio_channels", "mono")],
)
def test_rejects_raw_strings_for_enum_fields(
    metadata_kwargs: dict[str, Any], field_name: str, raw_value: str
) -> None:
    metadata_kwargs[field_name] = raw_value

    with pytest.raises(InvalidCallMetadataError, match=field_name):
        CallMetadata(**metadata_kwargs)


def test_enum_values_match_specification_strings() -> None:
    assert SourceType.RECORDER_APP.value == "recorder_app"
    assert SourceType.CDR_SOFTWARE.value == "cdr_software"
    assert AudioChannels.MONO.value == "mono"
    assert AudioChannels.STEREO.value == "stereo"


def test_rejects_naive_timestamp(metadata_kwargs: dict[str, Any]) -> None:
    metadata_kwargs["call_timestamp"] = datetime(2026, 7, 26, 9, 30)

    with pytest.raises(InvalidCallMetadataError, match="call_timestamp"):
        CallMetadata(**metadata_kwargs)


def test_rejects_timestamp_with_ineffective_timezone(metadata_kwargs: dict[str, Any]) -> None:
    metadata_kwargs["call_timestamp"] = datetime(2026, 7, 26, 9, 30, tzinfo=_IneffectiveTzinfo())

    with pytest.raises(InvalidCallMetadataError, match="call_timestamp"):
        CallMetadata(**metadata_kwargs)


def test_rejects_non_datetime_timestamp(metadata_kwargs: dict[str, Any]) -> None:
    metadata_kwargs["call_timestamp"] = "2026-07-26T09:30:00+00:00"

    with pytest.raises(InvalidCallMetadataError, match="call_timestamp"):
        CallMetadata(**metadata_kwargs)


@pytest.mark.parametrize(
    "bad_value",
    [True, False, "180", None, float("nan"), float("inf"), float("-inf"), -0.1],
)
def test_rejects_invalid_durations(metadata_kwargs: dict[str, Any], bad_value: object) -> None:
    metadata_kwargs["duration_seconds"] = bad_value

    with pytest.raises(InvalidCallMetadataError, match="duration_seconds"):
        CallMetadata(**metadata_kwargs)


def test_accepts_zero_duration(metadata_kwargs: dict[str, Any]) -> None:
    metadata_kwargs["duration_seconds"] = 0.0

    assert CallMetadata(**metadata_kwargs).duration_seconds == 0.0


def test_is_immutable(metadata_kwargs: dict[str, Any]) -> None:
    metadata = CallMetadata(**metadata_kwargs)

    with pytest.raises(AttributeError):
        metadata.call_id = "other"  # type: ignore[misc]


def test_repr_and_str_hide_pii(metadata_kwargs: dict[str, Any]) -> None:
    metadata = CallMetadata(**metadata_kwargs)

    for rendered in (repr(metadata), str(metadata)):
        assert "call-0001" in rendered
        assert metadata_kwargs["seller_number"] not in rendered
        assert metadata_kwargs["counterparty_phone"] not in rendered
        assert metadata_kwargs["original_filename"] not in rendered


def test_exception_messages_do_not_leak_field_values(metadata_kwargs: dict[str, Any]) -> None:
    metadata_kwargs["counterparty_phone"] = 5550000002

    with pytest.raises(InvalidCallMetadataError) as excinfo:
        CallMetadata(**metadata_kwargs)

    message = str(excinfo.value)
    assert "5550000002" not in message
    assert "counterparty_phone" in message
