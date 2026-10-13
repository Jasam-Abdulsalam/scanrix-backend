import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from app.core.config import settings

class MongoDB:
    client: AsyncIOMotorClient = None
    
def tls_options(url: str) -> dict:
    """CA bundle for TLS connections (Atlas). Passing any TLS option makes pymongo
    force TLS, which breaks a plain local mongod (docker-compose `mongodb://mongo:27017`)."""
    lowered = url.lower()
    uses_tls = lowered.startswith("mongodb+srv://") or "tls=true" in lowered or "ssl=true" in lowered
    return {"tlsCAFile": certifi.where()} if uses_tls else {}

async def connect_to_mongo():
    """Connect to MongoDB"""
    MongoDB.client = AsyncIOMotorClient(settings.MONGODB_URL, **tls_options(settings.MONGODB_URL))
    try:
        await MongoDB.client.admin.command('ping')
        print("✅ Connected to MongoDB")
    except Exception as e:
        # Never log the connection string: it contains the database password.
        print(f"❌ Failed to connect to MongoDB: {e}")

async def close_mongo_connection():
    """Close MongoDB connection"""
    MongoDB.client.close()
    print("❌ Closed MongoDB connection")

def get_database():
    """Get database instance"""
    return MongoDB.client[settings.DATABASE_NAME]