"""Unit tests for the faster-whisper adapter (no real model load)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionInputError,
    InvalidTranscriptionResponseError,
    TranscriptionProviderUnavailableError,
    TranscriptionRequestFailedError,
    UnsupportedTranscriptionLanguageError,
)
from sales_call_agent.transcription.models import (
    ConfidenceScale,
    TranscriptionQualityFlag,
    TranscriptionRequest,
)
from sales_call_agent.transcription.provider import run_transcription
from sales_call_agent.transcription.providers.faster_whisper import (
    FasterWhisperConfig,
    FasterWhisperConfigError,
    FasterWhisperTranscriptionProvider,
    _preflight_local_model_directory,
    default_faster_whisper_model_loader,
    privacy_safe_model_identity,
)


@dataclass(frozen=True, slots=True)
class _FakeWord:
    word: str
    start: float | None = None
    end: float | None = None
    probability: float | None = None


@dataclass(frozen=True, slots=True)
class _FakeSegment:
    text: str
    start: float
    end: float
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    words: tuple[_FakeWord, ...] | None = None


@dataclass(frozen=True, slots=True)
class _FakeInfo:
    language: str | None = "en"
    language_probability: float | None = 0.98


class _FakeModel:
    def __init__(self, payload: object, *, multilingual: bool = True) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []
        self.model = type("_Inner", (), {"is_multilingual": multilingual})()

    def transcribe(self, audio_path: str, **kwargs: object) -> object:
        self.calls.append({"audio_path": audio_path, **kwargs})
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _request(
    tmp_path: Path,
    *,
    text_file: bool = True,
    expected_language: str | None = "en",
) -> TranscriptionRequest:
    path = tmp_path / "normalized.asr.wav"
    if text_file:
        path.write_bytes(b"RIFF....WAVEfmt ")
    return TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path=str(path),
        normalized_audio_hash="abc123",
        expected_language=expected_language,
    )


def _provider(
    tmp_path: Path,
    payload: object,
    *,
    config: FasterWhisperConfig | None = None,
    multilingual: bool = True,
) -> tuple[FasterWhisperTranscriptionProvider, _FakeModel]:
    model = _FakeModel(payload, multilingual=multilingual)
    provider = FasterWhisperTranscriptionProvider(
        config or FasterWhisperConfig(local_files_only=True),
        model_loader=lambda _cfg: model,
    )
    return provider, model


def _write_complete_model_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / "model.bin").write_bytes(b"model")
    (path / "tokenizer.json").write_text("{}", encoding="utf-8")


def test_module_imports_without_optional_dependency() -> None:
    import sales_call_agent.transcription.providers.faster_whisper as module

    assert hasattr(module, "FasterWhisperTranscriptionProvider")


def test_missing_optional_dependency_fails_only_on_model_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str, package: str | None = None) -> object:
        raise ImportError(f"No module named {name}")

    monkeypatch.setattr(
        "sales_call_agent.transcription.providers.faster_whisper.importlib.import_module",
        fake_import_module,
    )
    with pytest.raises(TranscriptionProviderUnavailableError, match="optional dependency"):
        default_faster_whisper_model_loader(FasterWhisperConfig())


def test_config_rejects_boolean_for_integer_fields() -> None:
    with pytest.raises(FasterWhisperConfigError, match="beam_size"):
        FasterWhisperConfig(beam_size=True)  # type: ignore[arg-type]
    with pytest.raises(FasterWhisperConfigError, match="device_index"):
        FasterWhisperConfig(device_index=False)  # type: ignore[arg-type]
    with pytest.raises(FasterWhisperConfigError, match="cpu_threads"):
        FasterWhisperConfig(cpu_threads=True)  # type: ignore[arg-type]


def test_config_rejects_invalid_device() -> None:
    with pytest.raises(FasterWhisperConfigError, match="device"):
        FasterWhisperConfig(device="mps")


def test_valid_segment_and_word_mapping(tmp_path: Path) -> None:
    payload = (
        [
            _FakeSegment(
                text=" Hello",
                start=0.0,
                end=0.5,
                avg_logprob=-0.2,
                no_speech_prob=0.01,
                words=(_FakeWord(word=" Hello", start=0.0, end=0.5, probability=0.9),),
            ),
            _FakeSegment(
                text=", world!",
                start=0.5,
                end=1.0,
                avg_logprob=-0.3,
                no_speech_prob=0.02,
                words=(
                    _FakeWord(word=",", start=0.5, end=0.6, probability=0.8),
                    _FakeWord(word=" world!", start=0.6, end=1.0, probability=0.85),
                ),
            ),
        ],
        _FakeInfo(),
    )
    provider, model = _provider(tmp_path, payload)
    result = run_transcription(provider, _request(tmp_path))

    assert result.full_text == " Hello, world!"
    assert result.provider_confidence == ()
    assert len(result.segments) == 2
    assert result.segments[0].provider_confidence[0].name == "AVG_LOGPROB"
    assert result.segments[0].provider_confidence[0].scale is ConfidenceScale.LOG_PROBABILITY
    assert result.segments[0].provider_confidence[1].name == "NO_SPEECH_PROB"
    assert result.segments[0].words[0].provider_confidence[0].name == "WORD_PROBABILITY"
    assert model.calls  # inference happened


def test_no_result_level_aggregate_confidence(tmp_path: Path) -> None:
    payload = (
        [
            _FakeSegment(text="hi", start=0.0, end=0.4, avg_logprob=-0.1),
            _FakeSegment(text=" there", start=0.4, end=0.8, avg_logprob=-0.9),
        ],
        _FakeInfo(),
    )
    provider, _ = _provider(tmp_path, payload)
    result = run_transcription(provider, _request(tmp_path))
    assert result.provider_confidence == ()


def test_no_speech_when_no_segments(tmp_path: Path) -> None:
    provider, _ = _provider(tmp_path, ([], _FakeInfo()))
    result = run_transcription(provider, _request(tmp_path))
    assert result.full_text == ""
    assert result.segments == ()
    assert TranscriptionQualityFlag.NO_SPEECH_DETECTED in result.quality_flags


def test_whitespace_only_segments_become_no_speech(tmp_path: Path) -> None:
    payload = ([_FakeSegment(text="   ", start=0.0, end=0.5)], _FakeInfo())
    provider, _ = _provider(tmp_path, payload)
    result = run_transcription(provider, _request(tmp_path))
    assert result.full_text == ""
    assert TranscriptionQualityFlag.NO_SPEECH_DETECTED in result.quality_flags


def test_nonempty_text_not_discarded_due_to_no_speech_prob(tmp_path: Path) -> None:
    payload = (
        [_FakeSegment(text="hello", start=0.0, end=0.5, no_speech_prob=0.99)],
        _FakeInfo(),
    )
    provider, _ = _provider(tmp_path, payload)
    result = run_transcription(provider, _request(tmp_path))
    assert result.full_text == "hello"
    assert TranscriptionQualityFlag.NO_SPEECH_DETECTED not in result.quality_flags


def test_deterministic_full_text_with_leading_spaces_and_punctuation(tmp_path: Path) -> None:
    payload = (
        [
            _FakeSegment(text=" Hello", start=0.0, end=0.4),
            _FakeSegment(text="   ", start=0.4, end=0.5),
            _FakeSegment(text="?", start=0.5, end=0.6),
        ],
        _FakeInfo(),
    )
    provider, _ = _provider(tmp_path, payload)
    first = run_transcription(provider, _request(tmp_path))
    second = run_transcription(provider, _request(tmp_path))
    assert first.full_text == " Hello?"
    assert first.full_text == second.full_text


def test_model_loader_called_once_across_requests(tmp_path: Path) -> None:
    payload = ([_FakeSegment(text="a", start=0.0, end=0.2)], _FakeInfo())
    loads = {"count": 0}
    model = _FakeModel(payload)

    def loader(_cfg: FasterWhisperConfig) -> _FakeModel:
        loads["count"] += 1
        return model

    provider = FasterWhisperTranscriptionProvider(FasterWhisperConfig(), model_loader=loader)
    request = _request(tmp_path)
    run_transcription(provider, request)
    run_transcription(provider, request)
    assert loads["count"] == 1
    assert provider.model_load_count == 1


def test_missing_file_raises_invalid_input(tmp_path: Path) -> None:
    provider, _ = _provider(tmp_path, ([], _FakeInfo()))
    request = TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path=str(tmp_path / "missing.wav"),
        normalized_audio_hash="abc",
    )
    with pytest.raises(InvalidTranscriptionInputError, match="does not exist"):
        run_transcription(provider, request)


def test_empty_file_raises_invalid_input(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")
    provider, _ = _provider(tmp_path, ([], _FakeInfo()))
    request = TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path=str(path),
        normalized_audio_hash="abc",
    )
    with pytest.raises(InvalidTranscriptionInputError, match="empty"):
        run_transcription(provider, request)


def test_inference_runtime_error_maps_to_request_failed(tmp_path: Path) -> None:
    provider, _ = _provider(tmp_path, RuntimeError("cuda boom"))
    with pytest.raises(TranscriptionRequestFailedError, match="inference failed"):
        run_transcription(provider, _request(tmp_path))


def test_supported_language_is_accepted(tmp_path: Path) -> None:
    provider, model = _provider(
        tmp_path, ([_FakeSegment(text="hi", start=0.0, end=0.2)], _FakeInfo())
    )
    result = run_transcription(provider, _request(tmp_path, expected_language="fr"))
    assert result.full_text == "hi"
    assert model.calls[0]["language"] == "fr"


def test_unsupported_language_rejected_before_inference(tmp_path: Path) -> None:
    provider, model = _provider(
        tmp_path, ([_FakeSegment(text="hi", start=0.0, end=0.2)], _FakeInfo())
    )
    with pytest.raises(UnsupportedTranscriptionLanguageError, match="unsupported") as excinfo:
        run_transcription(provider, _request(tmp_path, expected_language="zz"))
    assert "zz" not in str(excinfo.value)
    assert model.calls == []


def test_value_error_containing_language_is_not_misclassified(tmp_path: Path) -> None:
    provider, _ = _provider(
        tmp_path,
        ValueError("invalid beam size for language decoding path"),
    )
    with pytest.raises(TranscriptionRequestFailedError, match="rejected"):
        run_transcription(provider, _request(tmp_path, expected_language="en"))


def test_english_only_model_rejects_non_english_expected_language(tmp_path: Path) -> None:
    provider, model = _provider(
        tmp_path,
        ([_FakeSegment(text="hi", start=0.0, end=0.2)], _FakeInfo()),
        config=FasterWhisperConfig(model_size_or_path="tiny.en", local_files_only=True),
    )
    with pytest.raises(UnsupportedTranscriptionLanguageError):
        run_transcription(provider, _request(tmp_path, expected_language="fr"))
    assert model.calls == []


def test_english_only_loaded_model_rejects_non_english_language(tmp_path: Path) -> None:
    provider, model = _provider(
        tmp_path,
        ([_FakeSegment(text="hi", start=0.0, end=0.2)], _FakeInfo()),
        multilingual=False,
    )
    with pytest.raises(UnsupportedTranscriptionLanguageError):
        run_transcription(provider, _request(tmp_path, expected_language="de"))
    assert model.calls == []


def test_named_model_identity_remains_readable() -> None:
    assert privacy_safe_model_identity("tiny") == "tiny"
    assert privacy_safe_model_identity("small.en") == "small.en"
    provider = FasterWhisperTranscriptionProvider(
        FasterWhisperConfig(model_size_or_path="base"),
        model_loader=lambda _cfg: _FakeModel(([], _FakeInfo())),
    )
    assert provider.model_name == "base"


def test_absolute_local_path_becomes_opaque_identity(tmp_path: Path) -> None:
    model_dir = tmp_path / "Users" / "alice" / "customer_acme_whisper"
    _write_complete_model_dir(model_dir)
    identity = privacy_safe_model_identity(str(model_dir))
    assert identity.startswith("local-model-")
    assert "alice" not in identity
    assert "acme" not in identity
    assert str(model_dir) not in identity
    assert identity == privacy_safe_model_identity(str(model_dir))

    provider = FasterWhisperTranscriptionProvider(
        FasterWhisperConfig(model_size_or_path=str(model_dir), local_files_only=True),
        model_loader=lambda _cfg: _FakeModel(([], _FakeInfo())),
    )
    assert provider.model_name == identity


def test_config_repr_hides_path_fields(tmp_path: Path) -> None:
    model_dir = tmp_path / "secret-cache" / "model-v1"
    download_root = tmp_path / "Users" / "bob" / ".cache" / "whisper"
    config = FasterWhisperConfig(
        model_size_or_path=str(model_dir),
        download_root=str(download_root),
        local_files_only=True,
    )
    rendered = repr(config) + str(config)
    assert str(model_dir) not in rendered
    assert str(download_root) not in rendered
    assert "secret-cache" not in rendered
    assert "bob" not in rendered


def test_result_and_provider_do_not_expose_local_paths(tmp_path: Path) -> None:
    model_dir = tmp_path / "Users" / "carol" / "private_model"
    _write_complete_model_dir(model_dir)
    provider, _ = _provider(
        tmp_path,
        ([_FakeSegment(text="ok", start=0.0, end=0.1)], _FakeInfo()),
        config=FasterWhisperConfig(model_size_or_path=str(model_dir), local_files_only=True),
    )
    result = run_transcription(provider, _request(tmp_path))
    assert result.model_name == provider.model_name
    assert result.model_name.startswith("local-model-")
    combined = repr(provider) + repr(result) + str(result)
    assert "carol" not in combined
    assert "private_model" not in combined
    assert str(model_dir) not in combined


def test_generator_runtime_error_after_yield_maps_to_request_failed(tmp_path: Path) -> None:
    def flaky_segments() -> Iterator[_FakeSegment]:
        yield _FakeSegment(text=" partial", start=0.0, end=0.2)
        raise RuntimeError("decode exploded")

    provider, _ = _provider(tmp_path, (flaky_segments(), _FakeInfo()))
    with pytest.raises(TranscriptionRequestFailedError, match="inference failed"):
        run_transcription(provider, _request(tmp_path))


def test_generator_oserror_before_yield_maps_to_request_failed(tmp_path: Path) -> None:
    def failing_segments() -> Iterator[_FakeSegment]:
        raise OSError("audio read failed")
        yield  # pragma: no cover

    provider, _ = _provider(tmp_path, (failing_segments(), _FakeInfo()))
    with pytest.raises(TranscriptionRequestFailedError, match="inference failed"):
        run_transcription(provider, _request(tmp_path))


def test_malformed_completed_payload_maps_to_invalid_response(tmp_path: Path) -> None:
    provider, _ = _provider(tmp_path, "not-a-tuple")
    with pytest.raises(InvalidTranscriptionResponseError, match="could not be mapped"):
        run_transcription(provider, _request(tmp_path))


def test_programming_error_is_not_broadly_wrapped(tmp_path: Path) -> None:
    class _BuggyModel:
        def transcribe(self, audio_path: str, **kwargs: object) -> object:
            raise KeyError("unexpected-bug")

    provider = FasterWhisperTranscriptionProvider(
        FasterWhisperConfig(), model_loader=lambda _cfg: _BuggyModel()
    )
    with pytest.raises(KeyError, match="unexpected-bug"):
        run_transcription(provider, _request(tmp_path))


def test_incomplete_local_model_directory_fails_before_model_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "Users" / "dave" / "incomplete_model"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.bin").write_bytes(b"x")
    # tokenizer.json intentionally missing

    constructed = {"count": 0}

    class _Boom:
        def __init__(self, *args: object, **kwargs: object) -> None:
            constructed["count"] += 1
            raise AssertionError("WhisperModel must not be constructed")

    class _FakeModule:
        WhisperModel = _Boom

    monkeypatch.setattr(
        "sales_call_agent.transcription.providers.faster_whisper.importlib.import_module",
        lambda name, package=None: _FakeModule(),
    )
    with pytest.raises(TranscriptionProviderUnavailableError, match="incomplete") as excinfo:
        default_faster_whisper_model_loader(
            FasterWhisperConfig(model_size_or_path=str(model_dir), local_files_only=True)
        )
    assert constructed["count"] == 0
    assert "dave" not in str(excinfo.value)
    assert str(model_dir) not in str(excinfo.value)


def test_complete_synthetic_directory_passes_preflight(tmp_path: Path) -> None:
    model_dir = tmp_path / "complete_model"
    _write_complete_model_dir(model_dir)
    _preflight_local_model_directory(
        FasterWhisperConfig(model_size_or_path=str(model_dir), local_files_only=True)
    )


def test_named_model_local_files_only_skips_directory_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    constructed = {"count": 0}

    class _FakeWhisper:
        def __init__(self, *args: object, **kwargs: object) -> None:
            constructed["count"] += 1
            assert kwargs.get("local_files_only") is True

        def transcribe(self, *args: object, **kwargs: object) -> object:
            return ([], _FakeInfo())

    class _FakeModule:
        WhisperModel = _FakeWhisper

    monkeypatch.setattr(
        "sales_call_agent.transcription.providers.faster_whisper.importlib.import_module",
        lambda name, package=None: _FakeModule(),
    )
    loaded = default_faster_whisper_model_loader(
        FasterWhisperConfig(model_size_or_path="tiny", local_files_only=True)
    )
    assert constructed["count"] == 1
    assert loaded is not None


def test_exception_messages_are_privacy_safe(tmp_path: Path) -> None:
    sensitive = tmp_path / "+15550001234_secret.wav"
    sensitive.write_bytes(b"")
    provider, _ = _provider(tmp_path, ([], _FakeInfo()))
    request = TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path=str(sensitive),
        normalized_audio_hash="abc",
    )
    with pytest.raises(InvalidTranscriptionInputError) as excinfo:
        run_transcription(provider, request)
    message = str(excinfo.value)
    assert "15550001234" not in message
    assert "secret.wav" not in message
    assert str(tmp_path) not in message


def test_warning_codes_for_config_flags(tmp_path: Path) -> None:
    path = tmp_path / "normalized.asr.wav"
    path.write_bytes(b"data")
    provider, _ = _provider(
        tmp_path,
        ([_FakeSegment(text="hi", start=0.0, end=0.2)], _FakeInfo()),
        config=FasterWhisperConfig(
            word_timestamps=False,
            vad_filter=True,
            default_language=None,
            local_files_only=True,
        ),
    )
    request = TranscriptionRequest(
        call_id="call-1",
        normalized_audio_path=str(path),
        normalized_audio_hash="abc",
        expected_language=None,
    )
    result = run_transcription(provider, request)
    assert "WORD_TIMESTAMPS_DISABLED" in result.warning_codes
    assert "VAD_FILTER_ENABLED" in result.warning_codes
    assert "LANGUAGE_AUTO_DETECTED" in result.warning_codes


def test_mixed_word_timings_fall_back_to_untimed_words(tmp_path: Path) -> None:
    payload = (
        [
            _FakeSegment(
                text="hello world",
                start=0.0,
                end=1.0,
                words=(
                    _FakeWord(word="hello", start=0.0, end=0.4, probability=0.9),
                    _FakeWord(word=" world"),  # missing timestamps
                ),
            )
        ],
        _FakeInfo(),
    )
    provider, _ = _provider(tmp_path, payload)
    result = run_transcription(provider, _request(tmp_path))
    assert all(word.start_seconds is None for word in result.segments[0].words)
