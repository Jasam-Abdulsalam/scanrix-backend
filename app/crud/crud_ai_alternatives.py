from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.db.mongodb import get_database


async def get_cached(cache_key: str) -> Optional[dict]:
    """Uses the unique cache_key index (see app/db/indexes.py)."""
    return await get_database().ai_product_alternatives.find_one({"cache_key": cache_key}, {"_id": 0})


async def save_alternatives(cache_key: str, result: dict, barcode: str, model: str) -> None:
    """First writer wins (atomic upsert): a concurrent duplicate never overwrites. The TTL index on
    expires_at removes the entry after AI_ALTERNATIVES_TTL_DAYS (prices and ranges go stale)."""
    now = datetime.now(timezone.utc)
    await get_database().ai_product_alternatives.update_one(
        {"cache_key": cache_key},
        {"$setOnInsert": {
            "cache_key": cache_key, "barcode": barcode, "result": result, "model": model, "created_at": now,
            "expires_at": now + timedelta(days=settings.AI_ALTERNATIVES_TTL_DAYS),
        }},
        upsert=True,
    )
