from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.ai_analysis import AIAnalyzeRequest

NATURAL_REMEDY_DISCLAIMER = ("AI suggestion, not verified by Scanrix and not medical advice. Homemade mixes can "
                             "still irritate or cause allergies.")
PATCH_TEST_NOTE = ("Patch test on your inner arm 24 hours before first use. Stop if it stings, itches or turns red. "
                   "Keep away from eyes.")

# Output limits for the AI answer. The prompt states the same numbers (an answer over a limit is rejected,
# never trimmed).
MAX_REMEDIES = 2
MAX_REMEDY_INGREDIENTS = 5
MAX_REMEDY_STEPS = 4
MAX_SHORT_CHARS = 80
MAX_LINE_CHARS = 200


class NaturalRemedyRequest(AIAnalyzeRequest):
    """Same source as 'Get AI verdict': a scanned product's barcode, or label (OCR) ingredient text +
    category. Only cosmetics get a remedy (checked by the service, so the barcode's own category counts)."""


class RemedyIngredient(BaseModel):
    item: str = Field(..., min_length=1, max_length=60, description="A kitchen ingredient, e.g. 'besan'")
    amount: str = Field(..., min_length=1, max_length=40, description="e.g. '2 tsp'")


class AINaturalRemedy(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_SHORT_CHARS, description="e.g. 'Besan and rose water cleanser'")
    replaces: str = Field(..., min_length=1, max_length=60, description="What it stands in for, e.g. 'face wash'")
    ingredients: List[RemedyIngredient] = Field(..., min_length=1, max_length=MAX_REMEDY_INGREDIENTS)
    steps: List[str] = Field(..., min_length=1, max_length=MAX_REMEDY_STEPS)
    how_often: str = Field(..., min_length=1, max_length=MAX_SHORT_CHARS)
    keeps_for: str = Field(..., min_length=1, max_length=MAX_SHORT_CHARS, description="e.g. 'Make fresh each time'")
    why: str = Field(..., min_length=1, max_length=MAX_LINE_CHARS)
    caution: Optional[str] = Field(None, max_length=MAX_LINE_CHARS)


class AINaturalRemedyResult(BaseModel):
    """What the AI returns. Validated; never trusted as-is (see ai_natural_remedy_rules.clean_result)."""
    product_type: str = Field(..., min_length=1, max_length=60)
    remedies: List[AINaturalRemedy] = Field(default_factory=list, max_length=MAX_REMEDIES)
    no_remedy_reason: Optional[str] = Field(None, max_length=MAX_LINE_CHARS,
                                            description="Why there is no remedy, when `remedies` is empty")


class AINaturalRemedyResponse(AINaturalRemedyResult):
    verified: bool = False
    source: str = "ai"
    cached: bool = False
    credits_remaining: Optional[int] = Field(None, description="Credits left this week (None when not looked up)")
    generated_at: Optional[datetime] = None
    disclaimer: str = NATURAL_REMEDY_DISCLAIMER
    patch_test_note: str = PATCH_TEST_NOTE
