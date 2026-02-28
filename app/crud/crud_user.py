from bson import ObjectId
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
        "preferences": {}
    }
    result = await db.users.insert_one(user_dict)
    user_dict["_id"] = result.inserted_id
    return user_dict

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