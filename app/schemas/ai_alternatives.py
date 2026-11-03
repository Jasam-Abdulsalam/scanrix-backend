from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

ALTERNATIVES_DISCLAIMER = ("AI suggestions. Not verified by Scanrix: names, prices and ingredients can be wrong. "
                           "Check the product's label before buying.")

# Output limits for the AI answer. The prompt states the same numbers, so they can't drift apart
# (an answer over a limit is rejected, never trimmed).
MAX_ALTERNATIVES = 3
MAX_NAME_CHARS = 120
MAX_WHY_CHARS = 200
MAX_AVOIDS = 5
MAX_PRICE_INR = 100_000


class AIAlternativesRequest(BaseModel):
    """Alternatives need a real product (its name, size and ingredients), so only a scanned barcode."""
    barcode: str = Field(..., min_length=4, max_length=64, pattern=r"^[A-Za-z0-9\-]+$")


class AIAlternative(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_CHARS)
    brand: str = Field(..., min_length=1, max_length=MAX_NAME_CHARS)
    size: Optional[str] = Field(None, max_length=40, description="e.g. '100 ml'")
    price_inr: Optional[int] = Field(None, ge=1, le=MAX_PRICE_INR, description="Approximate MRP, an AI estimate")
    why_better: str = Field(..., min_length=1, max_length=MAX_WHY_CHARS)
    avoids: List[str] = Field(default_factory=list, max_length=MAX_AVOIDS,
                              description="Flagged ingredients of the scanned product this one avoids")
    image_url: Optional[str] = Field(None, max_length=1000,
                                     description="Product photo found by name (https), or null. Added by the "
                                                 "backend, never taken from the AI")


class AIAlternativesResult(BaseModel):
    """What the AI returns. Validated; never trusted as-is."""
    product_type: str = Field(..., min_length=1, max_length=60)
    original_price_inr: Optional[int] = Field(None, ge=1, le=MAX_PRICE_INR)
    alternatives: List[AIAlternative] = Field(default_factory=list, max_length=MAX_ALTERNATIVES)


class AIAlternativesResponse(AIAlternativesResult):
    verified: bool = False
    source: str = "ai"
    cached: bool = False
    credits_remaining: Optional[int] = Field(None, description="Credits left this week (None when not looked up)")
    generated_at: Optional[datetime] = None
    disclaimer: str = ALTERNATIVES_DISCLAIMER
