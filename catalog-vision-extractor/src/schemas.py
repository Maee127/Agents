"""
Pydantic models that validate what the vision model returns, at the two
points where unvalidated JSON enters the pipeline:

- PageClassification: the classifier's response for one page.
- RawProductRow: one product row from the extractor's response.

RawProductRow is deliberately permissive about value types (a "number" field
may arrive as a string like "1.250,50") because cleaning values is the
normalizer's job. What it does enforce is *structure*: known keys, and that
a row is a JSON object rather than a stray string or list.
"""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.config import PAGE_TYPES

# Numeric catalogue fields may legitimately arrive as messy strings;
# the normalizer coerces them to floats later.
RawNumber = Optional[Union[float, int, str]]


class PageClassification(BaseModel):
    """Validated classifier output for a single page."""

    page_type: Literal[PAGE_TYPES]  # type: ignore[valid-type]
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class RawProductRow(BaseModel):
    """One raw product row as returned by the extraction prompt.

    Unknown keys are ignored rather than rejected so a slightly chatty model
    response doesn't invalidate an otherwise-good row.
    """

    model_config = ConfigDict(extra="ignore")

    sku: Optional[str] = None
    model_name: Optional[str] = None
    category: Optional[str] = None
    width_mm: RawNumber = None
    depth_mm: RawNumber = None
    height_mm: RawNumber = None
    net_weight_kg: RawNumber = None
    gross_weight_kg: RawNumber = None
    volume_l: RawNumber = None
    power_supply: Optional[str] = None
    power_consumption_w: RawNumber = None
    refrigerant_gas: Optional[str] = None
    energy_class: Optional[str] = None
    temperature_range: Optional[str] = None
    list_price: RawNumber = None
    currency: Optional[str] = None
    source_page: Optional[int] = None

    @field_validator(
        "sku",
        "model_name",
        "category",
        "power_supply",
        "refrigerant_gas",
        "energy_class",
        "temperature_range",
        "currency",
        mode="before",
    )
    @classmethod
    def _stringify_numbers(cls, value):
        # A purely numeric SKU (e.g. 40101) arrives as a JSON number; that's
        # a valid identifier, not a validation failure.
        if isinstance(value, bool):
            return value  # let pydantic reject it
        if isinstance(value, (int, float)):
            return str(value)
        return value


__all__ = ["PageClassification", "RawProductRow"]
