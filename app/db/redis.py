from upstash_redis import Redis
from app.core.config import settings

class RedisClient:
    """Upstash Redis Client"""
    _client = None

    @classmethod
    def get_client(cls) -> Redis:
        if cls._client is None:
            cls._client = Redis(
                url=settings.UPSTASH_REDIS_REST_URL,
                token=settings.UPSTASH_REDIS_REST_TOKEN
            )
            print("✅ Connected to Upstash Redis")
        return cls._client

def get_redis() -> Redis:
    return RedisClient.get_client()
