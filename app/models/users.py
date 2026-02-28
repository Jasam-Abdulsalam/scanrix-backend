from datetime import datetime
from typing import Optional

def user_helper(user) -> dict:
    """Convert MongoDB user document to dict"""
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user["name"],
        "hashed_password": user["hashed_password"],
        "created_at": user.get("created_at", datetime.utcnow()),
        "preferences": user.get("preferences", {}),
    }