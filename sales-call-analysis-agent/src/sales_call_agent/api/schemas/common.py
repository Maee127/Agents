"""Shared strict validators and base schema types for the v1 API."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SEMVER_CORE_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_WARNING_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_safe_identifier(v: str) -> str:
    if not _SAFE_IDENTIFIER_RE.fullmatch(v):
        raise ValueError("must be a safe identifier: start with alphanumeric, then [A-Za-z0-9._-]")
    if "/" in v or "\\" in v or ":" in v:
        raise ValueError("must not contain path-like characters")
    return v


def validate_semver(v: str) -> str:
    if not _SEMVER_CORE_RE.fullmatch(v):
        raise ValueError("must match MAJOR.MINOR.PATCH semver")
    return v


def validate_sha256_hex(v: str) -> str:
    if not _SHA256_HEX_RE.fullmatch(v):
        raise ValueError("must be a lowercase SHA-256 hex string (64 characters)")
    return v


class StrictApiModel(BaseModel):
    """Base for all strict API request/response models."""

    model_config = ConfigDict(strict=True, extra="forbid")


class RequestApiModel(BaseModel):
    """Base for API request models: extra fields forbidden, coercion allowed for JSON primitives."""

    model_config = ConfigDict(strict=False, extra="forbid")
