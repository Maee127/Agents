"""Behavioral tests for AudioAsset invariants."""

from typing import Any

import pytest

from sales_call_agent.domain import AudioAsset, AudioChannels, InvalidAudioAssetError


def test_constructs_with_valid_fields(audio_kwargs: dict[str, Any]) -> None:
    asset = AudioAsset(**audio_kwargs)

    assert asset.storage_path == audio_kwargs["storage_path"]
    assert asset.audio_channels is AudioChannels.MONO
    assert asset.content_hash == audio_kwargs["content_hash"]


@pytest.mark.parametrize("field_name", ["storage_path", "content_hash"])
@pytest.mark.parametrize("bad_value", ["", "   ", None, 123, b"raw-bytes"])
def test_rejects_invalid_required_strings(
    audio_kwargs: dict[str, Any], field_name: str, bad_value: object
) -> None:
    audio_kwargs[field_name] = bad_value

    with pytest.raises(InvalidAudioAssetError, match=field_name):
        AudioAsset(**audio_kwargs)


def test_rejects_raw_string_for_audio_channels(audio_kwargs: dict[str, Any]) -> None:
    audio_kwargs["audio_channels"] = "mono"

    with pytest.raises(InvalidAudioAssetError, match="audio_channels"):
        AudioAsset(**audio_kwargs)


def test_is_immutable(audio_kwargs: dict[str, Any]) -> None:
    asset = AudioAsset(**audio_kwargs)

    with pytest.raises(AttributeError):
        asset.content_hash = "tampered"  # type: ignore[misc]
