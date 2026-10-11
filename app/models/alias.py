from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class AliasBase(BaseModel):
    normalized_alias: str = Field(..., description="Normalized lowercase name without extra spaces/special chars")
    ingredient_id: str = Field(..., description="Foreign key referencing canonical ingredient _id")
    alias_type: str = Field(default="common_name", description="'common_name' | 'inci' | 'e_number' | 'trade_name' | 'cas'")

class AliasCreate(AliasBase):
    pass

class AliasInDB(AliasBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

def alias_helper(alias: dict) -> dict:
    """Convert MongoDB alias document to a clean dict"""
    return {
        "id": str(alias["_id"]),
        "normalized_alias": alias["normalized_alias"],
        "ingredient_id": str(alias["ingredient_id"]),
        "alias_type": alias.get("alias_type", "common_name"),
        "created_at": alias.get("created_at", datetime.utcnow()),
    }
