from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.db.mongodb import get_database


async def get_cached(cache_key: str) -> Optional[dict]:
    return await get_database().ai_product_analyses.find_one({"cache_key": cache_key}, {"_id": 0})


async def save_analysis(cache_key: str, analysis: dict, category: str, model: str,
                        barcode: Optional[str] = None) -> None:
    """First writer wins (atomic upsert): a concurrent duplicate never overwrites. TTL index on
    expires_at removes the entry after AI_ANALYSIS_TTL_DAYS."""
    now = datetime.now(timezone.utc)
    await get_database().ai_product_analyses.update_one(
        {"cache_key": cache_key},
        {"$setOnInsert": {
            "cache_key": cache_key, "barcode": barcode, "category": category, "analysis": analysis,
            "model": model, "reviewed": False, "created_at": now,
            "expires_at": now + timedelta(days=settings.AI_ANALYSIS_TTL_DAYS),
        }},
        upsert=True,
    )
