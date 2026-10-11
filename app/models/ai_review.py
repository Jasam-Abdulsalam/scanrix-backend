from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class AIReviewQueueBase(BaseModel):
    raw_ingredient_name: str = Field(..., description="The unrecognised label text scanned by user")
    suggested_canonical_name: Optional[str] = Field(None, description="AI-suggested standardized chemical name")
    category: Optional[str] = Field("unknown", description="Product category context (food, cosmetic, etc.)")
    proposed_facts: List[Dict[str, Any]] = Field(default_factory=list, description="List of proposed facts from AI")
    status: str = Field(default="pending", description="'pending' | 'approved' | 'rejected'")
    notes: Optional[str] = Field(None, description="Human reviewer notes or reason for rejection")

class AIReviewQueueCreate(AIReviewQueueBase):
    pass

class AIReviewQueueInDB(AIReviewQueueBase):
    id: str
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

def ai_review_helper(review: dict) -> dict:
    """Convert MongoDB AI review document to a clean dict"""
    return {
        "id": str(review["_id"]),
        "raw_ingredient_name": review["raw_ingredient_name"],
        "suggested_canonical_name": review.get("suggested_canonical_name"),
        "category": review.get("category", "unknown"),
        "proposed_facts": review.get("proposed_facts", []),
        "status": review.get("status", "pending"),
        "notes": review.get("notes"),
        "reviewed_at": review.get("reviewed_at"),
        "created_at": review.get("created_at", datetime.utcnow()),
    }
