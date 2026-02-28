from datetime import datetime

def history_helper(history) -> dict:
    """Convert MongoDB history document to dict"""
    return {
        "id": str(history["_id"]),
        "user_id": str(history["user_id"]),
        "product_id": str(history["product_id"]),
        "verdict": history.get("verdict"),
        "personalized_score": history.get("personalized_score"),
        "scanned_at": history.get("scanned_at", datetime.utcnow()),
    }