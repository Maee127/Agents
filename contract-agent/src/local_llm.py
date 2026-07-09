"""
Local LLM client: load Qwen2.5 from the project's qwen2.5-7b folder via
transformers and expose an OpenAI-compatible chat.completions interface.

OPTIMIZATIONS:
- GPU acceleration if CUDA is available (fallback to CPU)
- KV cache reuse for faster generation
- Device-aware tensor handling
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

_model = None
_tokenizer = None
_model_path: Path | None = None
_device: str | None = None


def default_model_path() -> Path:
    env = os.getenv("LOCAL_MODEL_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "qwen2.5-7b"


def _load() -> None:
    global _model, _tokenizer, _model_path, _device

    path = default_model_path()
    if _model is not None and _model_path == path:
        return

    if not path.is_dir():
        raise ValueError(
            f"Local model folder not found at {path}. "
            "Set LOCAL_MODEL_PATH in .env if the model lives elsewhere."
        )

    # Detect device: GPU if CUDA available, else CPU
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Loading model on device: {_device.upper()}")
    
    _tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    _model = AutoModelForCausalLM.from_pretrained(
        path,
        dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    _model.to(_device)
    _model.eval()
    _model_path = path


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _ChatCompletion:
    choices: list[_Choice]


class _Completions:
    def create(
        self,
        model: str | None = None,
        messages: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        **kwargs,
    ) -> _ChatCompletion:
        del model, kwargs
        _load()

        assert _model is not None and _tokenizer is not None
        assert messages is not None
        assert _device is not None

        prompt = _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = _tokenizer(prompt, return_tensors="pt").to(_device)

        gen_kwargs: dict = {
            "max_new_tokens": max_tokens,
            "pad_token_id": _tokenizer.eos_token_id,
            "use_cache": True,  # FIX 3: Enable KV cache reuse for faster generation
        }
        if temperature > 0:
            gen_kwargs["temperature"] = max(temperature, 1e-5)
            gen_kwargs["do_sample"] = True
        else:
            gen_kwargs["do_sample"] = False

        with torch.no_grad():
            output = _model.generate(**inputs, **gen_kwargs)

        new_tokens = output[0][inputs["input_ids"].shape[1] :]
        text = _tokenizer.decode(new_tokens, skip_special_tokens=True)

        return _ChatCompletion(
            choices=[_Choice(message=_Message(content=text))]
        )


class LocalLLMClient:
    """Drop-in replacement for OpenAI client.chat.completions."""

    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _Completions()})()
