from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class FactBase(BaseModel):
    ingredient_id: str = Field(..., description="Foreign key referencing canonical ingredient _id")
    source_id: str = Field(..., description="Foreign key referencing source _id (e.g. Prop 65, IARC)")
    dimension: str = Field(..., description="'cancer_class' | 'reproductive' | 'developmental' | 'regulatory' | 'allergen' | 'irritation'")
    value: str = Field(..., description="The objective finding (e.g. 'Group 1', 'listed_carcinogen', 'banned_in_cosmetics')")
    severity: str = Field(default="medium", description="'low' | 'medium' | 'high' | 'critical'")
    route: Optional[str] = Field(None, description="Exposure route if restricted: 'inhalation', 'oral', 'dermal', or 'all'")
    conditions: Optional[str] = Field(None, description="Specific conditions, e.g. 'rinse-off products only', 'max 0.1%'")
    evidence_tier: int = Field(default=2, ge=1, le=4, description="1=Regulatory Ban, 2=IARC/Prop65, 3=Expert Panel (CIR/SCCS), 4=AI Unverified")
    verified: bool = Field(default=True, description="True if from official regulatory/scientific source, False if AI generated")

class FactCreate(FactBase):
    pass

class FactInDB(FactBase):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

def fact_helper(fact: dict) -> dict:
    """Convert MongoDB fact document to a clean dict"""
    return {
        "id": str(fact["_id"]),
        "ingredient_id": str(fact["ingredient_id"]),
        "source_id": str(fact["source_id"]),
        "dimension": fact["dimension"],
        "value": fact["value"],
        "severity": fact.get("severity", "medium"),
        "route": fact.get("route"),
        "conditions": fact.get("conditions"),
        "evidence_tier": fact.get("evidence_tier", 2),
        "verified": fact.get("verified", True),
        "created_at": fact.get("created_at", datetime.utcnow()),
    }
