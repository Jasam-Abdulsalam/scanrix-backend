from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from app.core.config import settings

class MongoDB:
    client: AsyncIOMotorClient = None
    
async def connect_to_mongo():
    """Connect to MongoDB"""
    MongoDB.client = AsyncIOMotorClient(settings.MONGODB_URL)
    try:
        await MongoDB.client.admin.command('ping')
        print("✅ Connected to MongoDB")
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB ({settings.MONGODB_URL}): {e}")

async def close_mongo_connection():
    """Close MongoDB connection"""
    MongoDB.client.close()
    print("❌ Closed MongoDB connection")

def get_database():
    """Get database instance"""
    return MongoDB.client[settings.DATABASE_NAME]