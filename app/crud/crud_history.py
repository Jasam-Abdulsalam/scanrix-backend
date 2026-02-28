from bson import ObjectId
from app.db.mongodb import get_database
from datetime import datetime

async def create_history(user_id: str, product_id: str, verdict: str, personalized_score: int = None):
    """Create scan history entry"""
    db = get_database()
    history_data = {
        "user_id": ObjectId(user_id),
        "product_id": ObjectId(product_id),
        "verdict": verdict,
        "personalized_score": personalized_score,
        "scanned_at": datetime.utcnow()
    }
    result = await db.scan_history.insert_one(history_data)
    return result.inserted_id

async def get_user_history(user_id: str, limit: int = 50):
    """Get user's scan history"""
    db = get_database()
    history = await db.scan_history.find(
        {"user_id": ObjectId(user_id)}
    ).sort("scanned_at", -1).limit(limit).to_list(length=limit)
    return history