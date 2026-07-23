"""
Thin wrapper around the two supported vision APIs (Anthropic, OpenAI) so the
rest of the pipeline (classifier.py, extractor.py) never has to know which
provider is active. Both expose one function: call_vision(prompt, image_bytes)
-> raw text response.

Swapping providers is a single .env change (VISION_PROVIDER), not a code change.
"""
from __future__ import annotations

import base64

from src.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    VISION_PROVIDER,
)


def _call_anthropic(prompt: str, image_bytes: bytes) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        temperature=0,  # deterministic extraction — we want repeatable output, not creativity
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
    # Concatenate all text blocks in case the model splits its reply
    return "".join(block.text for block in response.content if block.type == "text")


def _call_openai(prompt: str, image_bytes: bytes) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=1500,
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
    return response.choices[0].message.content or ""


def _call_groq(prompt: str, image_bytes: bytes) -> str:
    from groq import Groq
    client = Groq()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    response = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            max_tokens=2048,
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
    return response.choices[0].message.content or ""  


    # completion = client.chat.completions.create(
    #     model="openai/gpt-oss-120b",
    #     messages=[
    #     {
    #         "role": "user",
    #         "content": ""
    #     }
    #     ],
    #     temperature=1,
    #     max_completion_tokens=2048,
    #     top_p=1,
    #     reasoning_effort="medium",
    #     stream=True,
    #     stop=None
    # )

    # for chunk in completion:
    #     return(chunk.choices[0].delta.content or "", end="")


def call_vision(prompt: str, image_bytes: bytes) -> str:
    """
    Send a single image + text prompt to the configured vision provider.
    Returns the raw text response — callers are responsible for parsing it
    (typically as JSON; see extractor.py's _parse_json_response).
    """
    if VISION_PROVIDER == "anthropic":
        return _call_anthropic(prompt, image_bytes)
    if VISION_PROVIDER == "openai":
        return _call_openai(prompt, image_bytes)
    if VISION_PROVIDER == "groq":
        return _call_groq(prompt, image_bytes)
    raise RuntimeError(f"Unknown VISION_PROVIDER: {VISION_PROVIDER}")
