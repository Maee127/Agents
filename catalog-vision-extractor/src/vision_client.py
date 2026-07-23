"""
Thin wrapper around the two supported vision APIs (Anthropic, OpenAI) so the
rest of the pipeline (classifier.py, extractor.py) never has to know which
provider is active. Both expose one function:
call_vision(prompt, image_bytes, max_tokens) -> raw text response.

Swapping providers is a single .env change (VISION_PROVIDER), not a code change.

Transient API failures (rate limits, timeouts, 5xx) are retried here with
exponential backoff. A truncated response (the model hit max_tokens mid-JSON)
raises VisionTruncatedError immediately — retrying the same request would
truncate again, so the caller must treat the page as failed instead of
silently losing rows.
"""
from __future__ import annotations

import base64
import time

from src.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    API_MAX_RETRIES,
    API_RETRY_BASE_DELAY,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    VISION_PROVIDER,
)


class VisionTruncatedError(RuntimeError):
    """The model stopped because it ran out of output tokens — response is incomplete."""


# Clients are created once and reused; both SDKs are thread-safe.
_anthropic_client = None
_openai_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _call_anthropic(prompt: str, image_bytes: bytes, max_tokens: int) -> str:
    client = _get_anthropic()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=0,  # deterministic extraction — repeatable output, not creativity
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    if response.stop_reason == "max_tokens":
        raise VisionTruncatedError(
            f"Anthropic response truncated at {max_tokens} tokens"
        )
    # Concatenate all text blocks in case the model splits its reply
    return "".join(block.text for block in response.content if block.type == "text")


def _call_openai(prompt: str, image_bytes: bytes, max_tokens: int) -> str:
    client = _get_openai()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ],
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise VisionTruncatedError(f"OpenAI response truncated at {max_tokens} tokens")
    return choice.message.content or ""


def call_vision(prompt: str, image_bytes: bytes, max_tokens: int) -> str:
    """
    Send a single image + text prompt to the configured vision provider.
    Returns the raw text response — callers are responsible for parsing it
    (typically as JSON; see classifier.py / extractor.py).

    Retries transient failures up to API_MAX_RETRIES times. Truncation is
    not retried (same request would truncate again) and propagates so the
    caller can mark the page as failed.
    """
    if VISION_PROVIDER == "anthropic":
        provider_call = _call_anthropic
    elif VISION_PROVIDER == "openai":
        provider_call = _call_openai
    else:
        raise RuntimeError(f"Unknown VISION_PROVIDER: {VISION_PROVIDER}")

    last_error: Exception | None = None
    for attempt in range(API_MAX_RETRIES):
        try:
            return provider_call(prompt, image_bytes, max_tokens)
        except VisionTruncatedError:
            raise
        except Exception as exc:  # noqa: BLE001 — SDK exception types vary by provider
            last_error = exc
            if attempt < API_MAX_RETRIES - 1:
                delay = API_RETRY_BASE_DELAY * (2**attempt)
                print(
                    f"[vision] attempt {attempt + 1}/{API_MAX_RETRIES} failed "
                    f"({type(exc).__name__}: {exc}); retrying in {delay:.0f}s"
                )
                time.sleep(delay)

    raise RuntimeError(
        f"Vision call failed after {API_MAX_RETRIES} attempts: {last_error}"
    ) from last_error
