"""
Page-hash-keyed cache so re-running the pipeline on an updated PDF only pays
for pages that actually changed. Each page's rendered-image hash is the key,
so even reordering pages within a PDF is handled correctly (the cache follows
the content, not the page number).

The key also includes a hash of the prompt + model that produced the result.
Without that, editing a prompt or switching models would silently keep
serving stale results until someone remembered to pass --no-cache.

Stored as one small JSON file per page under data/cache/<stage>/<key>.json
— simple, inspectable, no database needed for a project this size.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.config import CACHE_DIR


def context_hash(*parts: str) -> str:
    """Short stable hash of the prompt/model combination behind a cached result."""
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _cache_path(stage: str, page_hash: str, ctx: str) -> Path:
    stage_dir = CACHE_DIR / stage
    stage_dir.mkdir(parents=True, exist_ok=True)
    return stage_dir / f"{page_hash}-{ctx}.json"


def get_cached(stage: str, page_hash: str, ctx: str) -> Any | None:
    """Return the cached result for this page+stage+context, or None if not cached."""
    path = _cache_path(stage, page_hash, ctx)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        # Corrupt cache entry — treat as a miss rather than crashing the run.
        return None


def set_cached(stage: str, page_hash: str, ctx: str, result: Any) -> None:
    """Store a result for this page+stage+context."""
    path = _cache_path(stage, page_hash, ctx)
    path.write_text(json.dumps(result, indent=2))


def cache_stats(stage: str) -> dict[str, int]:
    """Quick count of how many entries are cached for a stage — used in CLI output."""
    stage_dir = CACHE_DIR / stage
    if not stage_dir.exists():
        return {"entries": 0}
    return {"entries": len(list(stage_dir.glob("*.json")))}
