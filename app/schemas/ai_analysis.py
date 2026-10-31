from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

DISCLAIMER = ("AI-generated estimate. It has not been verified by Scanrix, can be wrong, and is not medical advice. "
              "Our database result is shown separately.")

# Output limits for the AI answer. build_prompt tells the AI these same numbers, so the prompt and
# the validation below can't drift apart (an answer over a limit is rejected, never trimmed).
MAX_SUMMARY_CHARS = 500
MAX_CONCERNS = 8
MAX_POSITIVES = 5
MAX_INGREDIENT_CHARS = 80
MAX_EFFECT_CHARS = 200


class AIAnalyzeRequest(BaseModel):
    """Exactly one of: a scanned product's barcode, or OCR'd ingredient text (no product)."""
    barcode: Optional[str] = Field(None, min_length=4, max_length=64, pattern=r"^[A-Za-z0-9\-]+$")
    ingredients_text: Optional[str] = Field(None, min_length=5, max_length=4000)
    category: Literal["food", "cosmetic", "household"] = "food"  # used for text; a barcode uses the product's own

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.barcode) == bool(self.ingredients_text):
            raise ValueError("Send either 'barcode' or 'ingredients_text', not both and not neither")
        return self


class AIConcern(BaseModel):
    ingredient: str = Field(..., min_length=1, max_length=MAX_INGREDIENT_CHARS)
    effect: str = Field(..., min_length=1, max_length=MAX_EFFECT_CHARS, description="Plain-English, 'may' / 'commonly reported' wording")


class AIProductAnalysis(BaseModel):
    """What the AI says about the whole product. Validated; never trusted as-is."""
    verdict: Literal["good", "caution", "avoid", "unknown"]
    score: int = Field(..., ge=0, le=100)
    summary: str = Field(..., min_length=1, max_length=MAX_SUMMARY_CHARS)
    concerns: List[AIConcern] = Field(default_factory=list, max_length=MAX_CONCERNS)
    positives: List[str] = Field(default_factory=list, max_length=MAX_POSITIVES)
    certainty: Literal["well_known", "uncertain", "unknown"] = "uncertain"
    adjusted_by_database: bool = Field(False, description="True when our database hazards lowered the AI's verdict")


class AIAnalyzeResponse(AIProductAnalysis):
    verified: bool = False
    source: str = "ai"
    cached: bool = False
    credits_remaining: Optional[int] = Field(None, description="Credits left this week (None when not looked up)")
    generated_at: Optional[datetime] = None
    disclaimer: str = DISCLAIMER


class CreditsResponse(BaseModel):
    limit: int
    remaining: int
    resets_at: datetime
