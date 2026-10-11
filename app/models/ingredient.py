from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class IngredientMasterBase(BaseModel):
    canonical_name: str = Field(..., description="Standardized canonical lowercase name (e.g. 'acrylamide')")
    cas_number: Optional[str] = Field(None, description="Chemical Abstracts Service registry number (e.g. '79-06-1')")
    category: Optional[str] = Field(None, description="Broad category: 'food_additive', 'cosmetic_ingredient', 'preservative', etc.")
    description: Optional[str] = Field(None, description="Brief scientific or regulatory summary")

class IngredientMasterCreate(IngredientMasterBase):
    pass

class IngredientMasterInDB(IngredientMasterBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

def ingredient_helper(ingredient: dict) -> dict:
    """Convert MongoDB ingredient document to a clean dict"""
    return {
        "id": str(ingredient["_id"]),
        "canonical_name": ingredient["canonical_name"],
        "cas_number": ingredient.get("cas_number"),
        "category": ingredient.get("category"),
        "description": ingredient.get("description"),
        "created_at": ingredient.get("created_at", datetime.utcnow()),
    }
