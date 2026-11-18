from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Slot = Literal["morning", "evening"]
ProductType = Literal["cleanser", "toner", "serum", "moisturizer", "sunscreen", "other"]
BARCODE_PATTERN = r"^[A-Za-z0-9\-]+$"
MAX_ORDER_ITEMS = 50  # request-size guard; the real per-slot cap is settings.ROUTINE_MAX_PER_SLOT


class RoutineItemRead(BaseModel):
    """A product in a routine slot. verdict/overall_score are the product's STORED values (the product
    screen re-evaluates), same as a saved product."""
    barcode: str
    name: str
    brand: Optional[str] = None
    image_url: Optional[str] = None
    verdict: Optional[str] = None
    overall_score: Optional[int] = None
    product_type: Optional[ProductType] = None  # the user's label, same in both slots
    added_at: datetime


class RoutineRead(BaseModel):
    """The whole routine, steps in the user's order. Each slot is capped (ROUTINE_MAX_PER_SLOT), so this is
    a bounded response, not a paginated list."""
    morning: List[RoutineItemRead] = Field(default_factory=list)
    evening: List[RoutineItemRead] = Field(default_factory=list)


class RoutineOrderRequest(BaseModel):
    """The slot's barcodes in the new order. Must be exactly the slot's current products."""
    barcodes: List[str] = Field(..., max_length=MAX_ORDER_ITEMS)


class ProductTypeRequest(BaseModel):
    """The user's label for a product in their routine; null clears it."""
    product_type: Optional[ProductType] = None
