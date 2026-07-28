"""Local faster-whisper transcription adapter.

Implements ``TranscriptionProvider`` behind an injectable model-loader seam.
The optional ``faster-whisper`` dependency is imported only when a model is
loaded, so this module remains importable without the ``[asr]`` extra.
"""

from __future__ import annotations

import hashlib
import importlib
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sales_call_agent.transcription.exceptions import (
    InvalidTranscriptionInputError,
    InvalidTranscriptionResponseError,
    TranscriptionError,
    TranscriptionProviderUnavailableError,
    TranscriptionRequestFailedError,
    UnsupportedTranscriptionLanguageError,
)
from sales_call_agent.transcription.models import (
    ConfidenceScale,
    ProviderConfidenceMetric,
    TranscriptionQualityFlag,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegment,
    TranscriptWord,
)

_PROVIDER_NAME = "faster_whisper"
_ALLOWED_DEVICES = frozenset({"cpu", "cuda", "auto"})

# Published faster-whisper / Whisper language codes (frozen allowlist).
# Kept local so validation works without importing the optional ASR dependency.
_SUPPORTED_LANGUAGE_CODES = frozenset(
    {
        "af",
        "am",
        "ar",
        "as",
        "az",
        "ba",
        "be",
        "bg",
        "bn",
        "bo",
        "br",
        "bs",
        "ca",
        "cs",
        "cy",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fa",
        "fi",
        "fo",
        "fr",
        "gl",
        "gu",
        "ha",
        "haw",
        "he",
        "hi",
        "hr",
        "ht",
        "hu",
        "hy",
        "id",
        "is",
        "it",
        "ja",
        "jw",
        "ka",
        "kk",
        "km",
        "kn",
        "ko",
        "la",
        "lb",
        "ln",
        "lo",
        "lt",
        "lv",
        "mg",
        "mi",
        "mk",
        "ml",
        "mn",
        "mr",
        "ms",
        "mt",
        "my",
        "ne",
        "nl",
        "nn",
        "no",
        "oc",
        "pa",
        "pl",
        "ps",
        "pt",
        "ro",
        "ru",
        "sa",
        "sd",
        "si",
        "sk",
        "sl",
        "sn",
        "so",
        "sq",
        "sr",
        "su",
        "sv",
        "sw",
        "ta",
        "te",
        "tg",
        "th",
        "tk",
        "tl",
        "tr",
        "tt",
        "uk",
        "ur",
        "uz",
        "vi",
        "yi",
        "yo",
        "zh",
        "yue",
    }
)

# Named sizes from faster-whisper.utils._MODELS (readable public identity).
_KNOWN_MODEL_NAMES = frozenset(
    {
        "tiny.en",
        "tiny",
        "base.en",
        "base",
        "small.en",
        "small",
        "medium.en",
        "medium",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "distil-large-v2",
        "distil-medium.en",
        "distil-small.en",
        "distil-large-v3",
        "distil-large-v3.5",
        "large-v3-turbo",
        "turbo",
    }
)
_ENGLISH_ONLY_MODEL_NAMES = frozenset(name for name in _KNOWN_MODEL_NAMES if name.endswith(".en"))

_LOCAL_MODEL_REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json")


class FasterWhisperConfigError(InvalidTranscriptionInputError):
    """Raised when ``FasterWhisperConfig`` fails validation."""


@dataclass(frozen=True, slots=True, kw_only=True)
class FasterWhisperConfig:
    """Stable configuration for a faster-whisper provider instance."""

    model_size_or_path: str = field(default="tiny", repr=False)
    device: str = "cpu"
    compute_type: str = "int8"
    device_index: int = 0
    cpu_threads: int = 0
    beam_size: int = 5
    word_timestamps: bool = True
    vad_filter: bool = False
    download_root: str | None = field(default=None, repr=False)
    local_files_only: bool = True
    default_language: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_size_or_path, str) or not self.model_size_or_path.strip():
            raise FasterWhisperConfigError("model_size_or_path must be a non-empty string")
        if self.device not in _ALLOWED_DEVICES:
            raise FasterWhisperConfigError("device must be one of: cpu, cuda, auto")
        if not isinstance(self.compute_type, str) or not self.compute_type.strip():
            raise FasterWhisperConfigError("compute_type must be a non-empty string")
        _require_non_negative_int(self.device_index, "device_index")
        _require_non_negative_int(self.cpu_threads, "cpu_threads")
        _require_positive_int(self.beam_size, "beam_size")
        if not isinstance(self.word_timestamps, bool):
            raise FasterWhisperConfigError("word_timestamps must be a boolean")
        if not isinstance(self.vad_filter, bool):
            raise FasterWhisperConfigError("vad_filter must be a boolean")
        if self.download_root is not None and (
            not isinstance(self.download_root, str) or not self.download_root.strip()
        ):
            raise FasterWhisperConfigError("download_root must be None or a non-empty string")
        if not isinstance(self.local_files_only, bool):
            raise FasterWhisperConfigError("local_files_only must be a boolean")
        if self.default_language is not None and (
            not isinstance(self.default_language, str) or not self.default_language.strip()
        ):
            raise FasterWhisperConfigError("default_language must be None or a non-empty string")


@dataclass(frozen=True, slots=True, kw_only=True)
class _MappedWord:
    text: str
    start: float | None
    end: float | None
    probability: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _MappedSegment:
    text: str
    start: float
    end: float
    avg_logprob: float | None
    no_speech_prob: float | None
    words: tuple[_MappedWord, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class _MappedInfo:
    language: str | None
    language_probability: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _MappedTranscription:
    segments: tuple[_MappedSegment, ...]
    info: _MappedInfo


class _LoadedModel(Protocol):
    def transcribe(self, audio_path: str, **kwargs: object) -> object: ...


ModelLoader = Callable[[FasterWhisperConfig], _LoadedModel]


def _require_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FasterWhisperConfigError(f"{field_name} must be an integer")
    if value < 0:
        raise FasterWhisperConfigError(f"{field_name} must not be negative")


def _require_positive_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FasterWhisperConfigError(f"{field_name} must be an integer")
    if value <= 0:
        raise FasterWhisperConfigError(f"{field_name} must be greater than zero")


def privacy_safe_model_identity(model_size_or_path: str) -> str:
    """Return a stable, privacy-safe model identity for provider/result use."""
    raw = model_size_or_path.strip()
    if raw in _KNOWN_MODEL_NAMES:
        return raw
    if not _looks_like_filesystem_path(raw):
        return raw
    normalized = _normalized_path_string(raw)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"local-model-{digest}"


def _looks_like_filesystem_path(value: str) -> bool:
    path = Path(value)
    if path.is_absolute():
        return True
    if "\\" in value:
        return True
    try:
        return path.exists()
    except OSError:
        return False


def _normalized_path_string(value: str) -> str:
    path = Path(value).expanduser()
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _english_only_from_config(config: FasterWhisperConfig) -> bool | None:
    name = config.model_size_or_path.strip()
    if name in _ENGLISH_ONLY_MODEL_NAMES:
        return True
    if name in _KNOWN_MODEL_NAMES:
        return False
    return None


def _model_is_english_only(model: object) -> bool | None:
    """Return True/False when the loaded model exposes multilingual capability."""
    inner = getattr(model, "model", None)
    if inner is not None:
        flag = getattr(inner, "is_multilingual", None)
        if isinstance(flag, bool):
            return not flag
    flag = getattr(model, "is_multilingual", None)
    if isinstance(flag, bool):
        return not flag
    return None


def _validate_language_code(language: str | None, *, english_only: bool | None) -> None:
    if language is None:
        return
    if language not in _SUPPORTED_LANGUAGE_CODES:
        raise UnsupportedTranscriptionLanguageError("requested language is unsupported")
    if english_only is True and language != "en":
        raise UnsupportedTranscriptionLanguageError("requested language is unsupported")


def _preflight_local_model_directory(config: FasterWhisperConfig) -> None:
    """Reject incomplete local model dirs before WhisperModel can hit the network."""
    if not config.local_files_only:
        return
    path = Path(config.model_size_or_path)
    try:
        if not path.is_dir():
            return
    except OSError as error:
        raise TranscriptionProviderUnavailableError(
            "local faster-whisper model directory could not be read"
        ) from error

    for required_name in _LOCAL_MODEL_REQUIRED_FILES:
        candidate = path / required_name
        try:
            present = candidate.is_file()
        except OSError as error:
            raise TranscriptionProviderUnavailableError(
                "local faster-whisper model directory could not be read"
            ) from error
        if not present:
            raise TranscriptionProviderUnavailableError(
                "local faster-whisper model directory is incomplete for offline use"
            )


def _optional_ctranslate2_error_types() -> tuple[type[BaseException], ...]:
    """Best-effort CTranslate2 exception types without requiring the package."""
    try:
        module = importlib.import_module("ctranslate2")
    except ImportError:
        return ()
    collected: list[type[BaseException]] = []
    for attr_name in ("Error", "InternalError", "CudaError"):
        candidate = getattr(module, attr_name, None)
        if isinstance(candidate, type) and issubclass(candidate, BaseException):
            collected.append(candidate)
    return tuple(collected)


def default_faster_whisper_model_loader(config: FasterWhisperConfig) -> _LoadedModel:
    """Load a faster-whisper model, importing the optional dependency lazily."""
    _preflight_local_model_directory(config)

    try:
        module = importlib.import_module("faster_whisper")
    except ImportError as error:
        raise TranscriptionProviderUnavailableError(
            "faster-whisper optional dependency is not installed"
        ) from error

    whisper_model_cls = getattr(module, "WhisperModel", None)
    if whisper_model_cls is None:
        raise TranscriptionProviderUnavailableError(
            "faster-whisper optional dependency is not installed"
        )

    try:
        loaded: _LoadedModel = whisper_model_cls(
            config.model_size_or_path,
            device=config.device,
            device_index=config.device_index,
            compute_type=config.compute_type,
            cpu_threads=config.cpu_threads,
            download_root=config.download_root,
            local_files_only=config.local_files_only,
        )
    except ValueError as error:
        raise TranscriptionProviderUnavailableError(
            "faster-whisper configuration is unsupported"
        ) from error
    except (OSError, RuntimeError) as error:
        raise TranscriptionProviderUnavailableError(
            "faster-whisper model could not be loaded"
        ) from error
    return loaded


class FasterWhisperTranscriptionProvider:
    """TranscriptionProvider adapter for local faster-whisper inference."""

    def __init__(
        self,
        config: FasterWhisperConfig,
        *,
        model_loader: ModelLoader | None = None,
    ) -> None:
        if not isinstance(config, FasterWhisperConfig):
            raise FasterWhisperConfigError("config must be a FasterWhisperConfig")
        self._config = config
        self._model_loader = model_loader or default_faster_whisper_model_loader
        self._model: _LoadedModel | None = None
        self._model_load_count = 0
        self._model_identity = privacy_safe_model_identity(config.model_size_or_path)

    @property
    def provider_name(self) -> str:
        return _PROVIDER_NAME

    @property
    def model_name(self) -> str:
        return self._model_identity

    @property
    def model_load_count(self) -> int:
        """Number of times the model loader has been invoked (test seam)."""
        return self._model_load_count

    def warmup(self) -> None:
        """Eagerly load the model without running transcription."""
        self._ensure_model()

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        _validate_request_artifact(request)
        language = self._resolve_language(request)
        _validate_language_code(language, english_only=_english_only_from_config(self._config))

        model = self._ensure_model()
        _validate_language_code(language, english_only=_model_is_english_only(model))

        started = time.perf_counter()
        inference_errors: tuple[type[BaseException], ...] = (
            OSError,
            RuntimeError,
            *_optional_ctranslate2_error_types(),
        )
        try:
            raw = model.transcribe(
                request.normalized_audio_path,
                language=language,
                beam_size=self._config.beam_size,
                word_timestamps=self._config.word_timestamps,
                vad_filter=self._config.vad_filter,
            )
            raw = _materialize_provider_output(raw)
        except TranscriptionError:
            raise
        except ValueError as error:
            raise TranscriptionRequestFailedError(
                "faster-whisper rejected the transcription request"
            ) from error
        except inference_errors as error:
            raise TranscriptionRequestFailedError("faster-whisper inference failed") from error
        elapsed = time.perf_counter() - started

        try:
            mapped = _map_raw_transcription(raw)
            return _build_result(
                request=request,
                mapped=mapped,
                provider_name=self.provider_name,
                model_name=self.model_name,
                processing_duration_seconds=elapsed,
                word_timestamps_enabled=self._config.word_timestamps,
                vad_filter_enabled=self._config.vad_filter,
                language_was_auto=language is None,
            )
        except TranscriptionError:
            raise
        except (TypeError, AttributeError, KeyError, ValueError) as error:
            raise InvalidTranscriptionResponseError(
                "faster-whisper response could not be mapped"
            ) from error

    def _ensure_model(self) -> _LoadedModel:
        if self._model is None:
            self._model = self._model_loader(self._config)
            self._model_load_count += 1
        return self._model

    def _resolve_language(self, request: TranscriptionRequest) -> str | None:
        return request.expected_language or self._config.default_language


def _validate_request_artifact(request: TranscriptionRequest) -> None:
    path = Path(request.normalized_audio_path)
    if not path.is_file():
        raise InvalidTranscriptionInputError(
            "normalized audio file does not exist or is not a regular file"
        )
    if path.stat().st_size <= 0:
        raise InvalidTranscriptionInputError("normalized audio file is empty")


def _materialize_provider_output(raw: object) -> object:
    """Consume segment generators inside the inference error boundary.

    Returns a tuple of ``(tuple[segments], info)`` when the provider shape is
    recognizable; otherwise returns ``raw`` unchanged for mapping to reject.
    """
    if not isinstance(raw, tuple) or len(raw) != 2:
        return raw
    segments_obj, info_obj = raw
    if segments_obj is None:
        return ((), info_obj)
    if isinstance(segments_obj, str | bytes):
        return raw
    if isinstance(segments_obj, tuple | list):
        return (tuple(segments_obj), info_obj)
    if not isinstance(segments_obj, Iterable):
        return raw
    return (tuple(segments_obj), info_obj)


def _map_raw_transcription(raw: object) -> _MappedTranscription:
    if not isinstance(raw, tuple) or len(raw) != 2:
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    segments_obj, info_obj = raw
    segments = tuple(_map_segment(item) for item in _as_iterable(segments_obj))
    return _MappedTranscription(segments=segments, info=_map_info(info_obj))


def _as_iterable(value: object) -> Iterable[object]:
    if value is None:
        return ()
    if isinstance(value, str | bytes):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if not isinstance(value, Iterable):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    return value


def _map_info(info: object) -> _MappedInfo:
    language = getattr(info, "language", None)
    language_probability = getattr(info, "language_probability", None)
    if language is not None and (not isinstance(language, str) or not language.strip()):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if language_probability is not None and (
        isinstance(language_probability, bool) or not isinstance(language_probability, int | float)
    ):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    return _MappedInfo(
        language=language,
        language_probability=float(language_probability)
        if language_probability is not None
        else None,
    )


def _map_segment(segment: object) -> _MappedSegment:
    text = getattr(segment, "text", None)
    start = getattr(segment, "start", None)
    end = getattr(segment, "end", None)
    if not isinstance(text, str):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if isinstance(start, bool) or not isinstance(start, int | float):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if isinstance(end, bool) or not isinstance(end, int | float):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")

    avg_logprob = getattr(segment, "avg_logprob", None)
    no_speech_prob = getattr(segment, "no_speech_prob", None)
    if avg_logprob is not None and (
        isinstance(avg_logprob, bool) or not isinstance(avg_logprob, int | float)
    ):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if no_speech_prob is not None and (
        isinstance(no_speech_prob, bool) or not isinstance(no_speech_prob, int | float)
    ):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")

    words_raw = getattr(segment, "words", None)
    words: list[_MappedWord] = []
    if words_raw is not None:
        for word in _as_iterable(words_raw):
            words.append(_map_word(word))

    return _MappedSegment(
        text=text,
        start=float(start),
        end=float(end),
        avg_logprob=float(avg_logprob) if avg_logprob is not None else None,
        no_speech_prob=float(no_speech_prob) if no_speech_prob is not None else None,
        words=tuple(words),
    )


def _map_word(word: object) -> _MappedWord:
    text = getattr(word, "word", None)
    if text is None:
        text = getattr(word, "text", None)
    start = getattr(word, "start", None)
    end = getattr(word, "end", None)
    probability = getattr(word, "probability", None)
    if not isinstance(text, str):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if start is not None and (isinstance(start, bool) or not isinstance(start, int | float)):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if end is not None and (isinstance(end, bool) or not isinstance(end, int | float)):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    if probability is not None and (
        isinstance(probability, bool) or not isinstance(probability, int | float)
    ):
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    return _MappedWord(
        text=text,
        start=float(start) if start is not None else None,
        end=float(end) if end is not None else None,
        probability=float(probability) if probability is not None else None,
    )


def _build_result(
    *,
    request: TranscriptionRequest,
    mapped: _MappedTranscription,
    provider_name: str,
    model_name: str,
    processing_duration_seconds: float,
    word_timestamps_enabled: bool,
    vad_filter_enabled: bool,
    language_was_auto: bool,
) -> TranscriptionResult:
    accepted_segments: list[TranscriptSegment] = []
    accepted_texts: list[str] = []

    for mapped_segment in mapped.segments:
        if not mapped_segment.text.strip():
            continue
        segment = _to_transcript_segment(mapped_segment)
        accepted_segments.append(segment)
        accepted_texts.append(mapped_segment.text)

    warning_codes = _warning_codes(
        word_timestamps_enabled=word_timestamps_enabled,
        vad_filter_enabled=vad_filter_enabled,
        language_was_auto=language_was_auto,
    )

    if not accepted_segments:
        return TranscriptionResult(
            call_id=request.call_id,
            full_text="",
            segments=(),
            detected_language=mapped.info.language,
            language_confidence=mapped.info.language_probability,
            provider_name=provider_name,
            model_name=model_name,
            processing_duration_seconds=processing_duration_seconds,
            quality_flags=(TranscriptionQualityFlag.NO_SPEECH_DETECTED,),
            warning_codes=warning_codes,
        )

    return TranscriptionResult(
        call_id=request.call_id,
        full_text=_join_full_text(accepted_texts),
        segments=tuple(accepted_segments),
        detected_language=mapped.info.language,
        language_confidence=mapped.info.language_probability,
        provider_name=provider_name,
        model_name=model_name,
        processing_duration_seconds=processing_duration_seconds,
        warning_codes=warning_codes,
    )


def _to_transcript_segment(mapped_segment: _MappedSegment) -> TranscriptSegment:
    provider_confidence: list[ProviderConfidenceMetric] = []
    if mapped_segment.avg_logprob is not None:
        provider_confidence.append(
            ProviderConfidenceMetric(
                name="AVG_LOGPROB",
                value=mapped_segment.avg_logprob,
                scale=ConfidenceScale.LOG_PROBABILITY,
                higher_is_better=True,
            )
        )
    if mapped_segment.no_speech_prob is not None:
        provider_confidence.append(
            ProviderConfidenceMetric(
                name="NO_SPEECH_PROB",
                value=mapped_segment.no_speech_prob,
                scale=ConfidenceScale.ZERO_TO_ONE,
                higher_is_better=False,
            )
        )

    words = _to_transcript_words(mapped_segment.words)
    return TranscriptSegment(
        text=mapped_segment.text,
        start_seconds=mapped_segment.start,
        end_seconds=mapped_segment.end,
        words=words,
        provider_confidence=tuple(provider_confidence),
    )


def _to_transcript_words(words: Sequence[_MappedWord]) -> tuple[TranscriptWord, ...]:
    if not words:
        return ()

    usable = [word for word in words if word.text.strip()]
    if not usable:
        return ()

    # Existing model invariant: within one segment, all timed or all untimed.
    emit_timestamps = all(word.start is not None and word.end is not None for word in usable)

    result: list[TranscriptWord] = []
    for word in usable:
        metrics: tuple[ProviderConfidenceMetric, ...] = ()
        if word.probability is not None:
            metrics = (
                ProviderConfidenceMetric(
                    name="WORD_PROBABILITY",
                    value=word.probability,
                    scale=ConfidenceScale.ZERO_TO_ONE,
                    higher_is_better=True,
                ),
            )
        if emit_timestamps:
            word_start = word.start
            word_end = word.end
            if word_start is None or word_end is None:
                raise InvalidTranscriptionResponseError(
                    "faster-whisper response could not be mapped"
                )
            result.append(
                TranscriptWord(
                    text=word.text,
                    start_seconds=word_start,
                    end_seconds=word_end,
                    provider_confidence=metrics,
                )
            )
        else:
            result.append(TranscriptWord(text=word.text, provider_confidence=metrics))
    return tuple(result)


def _join_full_text(segment_texts: Sequence[str]) -> str:
    """Deterministically join accepted provider segment texts.

    Concatenates provider text without inserting artificial separators. Leading
    whitespace and punctuation are preserved when present in segment texts.
    """
    if not segment_texts:
        return ""
    joined = "".join(segment_texts)
    if joined and not joined.strip():
        raise InvalidTranscriptionResponseError("faster-whisper response could not be mapped")
    return joined


def _warning_codes(
    *,
    word_timestamps_enabled: bool,
    vad_filter_enabled: bool,
    language_was_auto: bool,
) -> tuple[str, ...]:
    codes: list[str] = []
    if not word_timestamps_enabled:
        codes.append("WORD_TIMESTAMPS_DISABLED")
    if vad_filter_enabled:
        codes.append("VAD_FILTER_ENABLED")
    if language_was_auto:
        codes.append("LANGUAGE_AUTO_DETECTED")
    return tuple(codes)
