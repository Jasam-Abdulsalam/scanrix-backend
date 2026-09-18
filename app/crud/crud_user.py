from bson import ObjectId
from pymongo import ReturnDocument
from typing import Optional
from app.db.mongodb import get_database
from app.schemas.user import UserCreate
from app.core.security import get_password_hash
from datetime import datetime

async def create_user(user: UserCreate):
    """Create a new user"""
    db = get_database()
    user_dict = {
        "email": user.email,
        "name": user.name,
        "hashed_password": get_password_hash(user.password),
        "created_at": datetime.utcnow(),
        "preferences": {},
        "photo_url": None,
        # Registration collects name directly, so there's nothing left to complete.
        "profile_completed": True,
    }
    result = await db.users.insert_one(user_dict)
    user_dict["_id"] = result.inserted_id
    return user_dict

async def create_google_user(email: str, name: str, google_id: str):
    """Create a user that signed up via Google Sign-In (no password)."""
    db = get_database()
    user_dict = {
        "email": email,
        "name": name,
        "hashed_password": None,
        "auth_provider": "google",
        "google_id": google_id,
        "created_at": datetime.utcnow(),
        "preferences": {},
        "photo_url": None,
        # Name comes from the Google profile but hasn't been confirmed by the
        # user yet, and no photo is captured at creation.
        "profile_completed": False,
    }
    result = await db.users.insert_one(user_dict)
    user_dict["_id"] = result.inserted_id
    return user_dict

async def update_user_profile(user_id: str, name: str, photo_url: Optional[str] = None):
    """Update a user's name/photo and mark their profile as completed."""
    db = get_database()
    user = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": {"name": name, "photo_url": photo_url, "profile_completed": True}},
        return_document=ReturnDocument.AFTER,
    )
    return user

async def delete_user(user_id: str):
    """Permanently delete a user's account"""
    db = get_database()
    result = await db.users.delete_one({"_id": ObjectId(user_id)})
    return result.deleted_count

async def get_user_by_email(email: str):
    """Get user by email"""
    db = get_database()
    user = await db.users.find_one({"email": email})
    return user

async def get_user_by_id(user_id: str):
    """Get user by ID"""
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    return user