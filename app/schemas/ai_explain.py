import re
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

NAME_PATTERN = re.compile(r"^[A-Za-z0-9 ,.()\-/'&%+]{2,80}$")
MAX_INGREDIENTS = 10


class AIExplainRequest(BaseModel):
    """Names the user chose to have explained: the "not assessed" ones from a scan result."""
    ingredients: List[str] = Field(..., min_length=1, max_length=MAX_INGREDIENTS)
    category: Literal["food", "cosmetic", "household"] = "food"

    @field_validator("ingredients")
    @classmethod
    def names_are_plain_ingredient_text(cls, names: List[str]) -> List[str]:
        # Names go into an AI prompt: only short, plain label text is accepted.
        for name in names:
            if not NAME_PATTERN.match(name.strip()):
                raise ValueError("Each ingredient must be 2-80 plain characters (letters, digits, spaces, , . ( ) - / ' & % +)")
        return [n.strip() for n in names]


class AIExplanationItem(BaseModel):
    """What the AI says about ONE ingredient. Always unverified; never part of the verdict."""
    name: str = Field(..., max_length=80)
    summary: str = Field(..., min_length=1, max_length=400, description="1-2 plain-English sentences: what it is")
    used_for: List[str] = Field(default_factory=list, max_length=5)
    possible_effects: List[str] = Field(default_factory=list, max_length=5, description="Commonly reported effects; empty if none known")
    certainty: Literal["well_known", "uncertain", "unknown"] = "uncertain"


class AIExplainResponse(BaseModel):
    explanations: List[AIExplanationItem] = Field(default_factory=list)
    already_assessed: List[str] = Field(default_factory=list, description="Names our database now recognises: use the normal result")
    unavailable: List[str] = Field(default_factory=list, description="Names the AI gave no usable answer for")
    verified: bool = False
    source: str = "ai"
    disclaimer: str = "AI-generated explanation. It has not been verified by Scanrix, can be wrong, and does not affect the safety score. Not medical advice."
