from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from app.db.mongodb import get_database
from app.api.deps import get_current_user

router = APIRouter()

class ReviewDecisionRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Optional notes or rationale for approval/rejection")

@router.get("/queue")
async def list_ai_review_queue(
    status: str = Query("pending", description="'pending' | 'approved' | 'rejected' | 'all'"),
    limit: int = Query(50, ge=1, le=200),
    current_user = Depends(get_current_user)
):
    """
    List AI fallback proposals awaiting human review or already processed.
    """
    db = get_database()
    query = {} if status == "all" else {"status": status}
    
    cursor = db.ai_review_queue.find(query).sort("created_at", -1).limit(limit)
    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
            "raw_ingredient_name": doc["raw_ingredient_name"],
            "suggested_canonical_name": doc.get("suggested_canonical_name"),
            "category": doc.get("category"),
            "proposed_facts": doc.get("proposed_facts", []),
            "status": doc.get("status", "pending"),
            "notes": doc.get("notes"),
            "created_at": doc.get("created_at"),
            "reviewed_at": doc.get("reviewed_at")
        })
        
    return {
        "status": status,
        "count": len(items),
        "items": items
    }

@router.post("/queue/{review_id}/approve")
async def approve_ai_proposal(
    review_id: str,
    decision: ReviewDecisionRequest,
    current_user = Depends(get_current_user)
):
    """
    Approve an AI proposal:
    1. Sets status to 'approved'
    2. Promotes the associated facts from Tier 4 (Unverified) to Tier 3 (Human Reviewed)
    3. Sets verified = True
    """
    db = get_database()
    try:
        obj_id = ObjectId(review_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review ID format")
        
    item = await db.ai_review_queue.find_one({"_id": obj_id})
    if not item:
        raise HTTPException(status_code=404, detail="Review queue item not found")
        
    canonical_name = item.get("suggested_canonical_name") or item["raw_ingredient_name"]
    
    # Update review queue status
    await db.ai_review_queue.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "approved",
            "notes": decision.notes,
            "reviewed_at": datetime.utcnow()
        }}
    )
    
    # Find the ingredient record to promote its facts
    ing = await db.ingredients.find_one({"canonical_name": canonical_name})
    if ing:
        ing_id = str(ing["_id"])
        # Promote facts to Tier 3 (Human-reviewed) and verified=True
        await db.facts.update_many(
            {"ingredient_id": ing_id, "evidence_tier": 4},
            {"$set": {
                "evidence_tier": 3,
                "verified": True,
                "promoted_at": datetime.utcnow()
            }}
        )

    return {
        "success": True,
        "message": f"Proposal for '{item['raw_ingredient_name']}' approved and promoted to Tier 3 verified."
    }

@router.post("/queue/{review_id}/reject")
async def reject_ai_proposal(
    review_id: str,
    decision: ReviewDecisionRequest,
    current_user = Depends(get_current_user)
):
    """
    Reject an AI proposal (hallucination or invalid chemical):
    1. Sets status to 'rejected'
    2. Removes any Tier 4 unverified facts created by AI so they do not flag future scans
    """
    db = get_database()
    try:
        obj_id = ObjectId(review_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review ID format")
        
    item = await db.ai_review_queue.find_one({"_id": obj_id})
    if not item:
        raise HTTPException(status_code=404, detail="Review queue item not found")
        
    canonical_name = item.get("suggested_canonical_name") or item["raw_ingredient_name"]

    # Mark as rejected
    await db.ai_review_queue.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "rejected",
            "notes": decision.notes,
            "reviewed_at": datetime.utcnow()
        }}
    )

    # Delete unverified Tier 4 facts associated with this proposal
    ing = await db.ingredients.find_one({"canonical_name": canonical_name})
    if ing:
        ing_id = str(ing["_id"])
        await db.facts.delete_many({"ingredient_id": ing_id, "evidence_tier": 4})

    return {
        "success": True,
        "message": f"Proposal for '{item['raw_ingredient_name']}' rejected and unverified facts cleaned up."
    }
