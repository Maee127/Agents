from __future__ import annotations

from typing import Optional, Dict, Literal

from pydantic import BaseModel, Field, field_validator


class Dimensions(BaseModel):
    """Optional numeric dimensions and weights standardized to common units.

    Use millimetres for linear dimensions and kilograms for weights.
    """

    width_mm: Optional[float] = None
    depth_mm: Optional[float] = None
    height_mm: Optional[float] = None
    net_weight_kg: Optional[float] = None
    gross_weight_kg: Optional[float] = None
    volume_l: Optional[float] = None


class ExtractedRow(BaseModel):
    """Canonical schema for one normalized product row extracted from a price table.

    This model is intentionally conservative: most fields are optional because
    real-world catalogues are sparse and different brands provide different
    columns. The normalizer should produce instances of this model before
    the exporter writes to Excel.
    """

    brand: str
    sku: str
    model_name: str
    product_family: Optional[str] = None
    product_category: Optional[str] = None
    dimensions: Optional[Dimensions] = None
    power_supply: Optional[str] = None
    power_consumption_w: Optional[float] = None
    refrigerant_gas: Optional[str] = None
    energy_class: Optional[str] = None
    temperature_range_c: Optional[str] = None
    list_price: Optional[float] = None
    currency: Optional[str] = None
    price_list_version: Optional[str] = None
    price_list_date: Optional[str] = None
    source_page: Optional[int] = None
    notes: Optional[str] = None
    raw: Optional[Dict] = None

    @field_validator("list_price")
    @classmethod
    def _price_non_negative(cls, v):
        if v is None:
            return v
        if v < 0:
            raise ValueError("list_price must be non-negative")
        return v

    @field_validator("source_page")
    @classmethod
    def _source_page_positive(cls, v):
        if v is None:
            return v
        if not isinstance(v, int) or v <= 0:
            raise ValueError("source_page must be a positive integer")
        return v


class PageClassification(BaseModel):
    page_type: Literal["intro", "spec", "drawing", "price_table"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    page_number: int

    @field_validator("page_number")
    @classmethod
    def _page_number_positive(cls, v):
        if v <= 0:
            raise ValueError("page_number must be a positive integer")
        return v


__all__ = ["Dimensions", "ExtractedRow", "PageClassification"]
