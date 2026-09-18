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
        "photo_url": user.get("photo_url"),
        # Docs that predate this field never went through onboarding, so
        # treat them as already complete rather than retroactively forcing
        # a flow they were never shown.
        "profile_completed": user.get("profile_completed", True),
    }