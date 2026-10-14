from datetime import datetime, timezone
from typing import Dict, Iterable, List

from pymongo import UpdateOne

from app.db.mongodb import get_database


async def find_cached(names: Iterable[str], category: str) -> Dict[str, dict]:
    """name -> stored explanation, in ONE query (no per-name lookups)."""
    cursor = get_database().ai_explanations.find({"name": {"$in": list(names)}, "category": category}, {"_id": 0})
    return {doc["name"]: doc async for doc in cursor}


async def save_explanations(items: List[dict], category: str, model: str) -> None:
    """Atomic upsert per name; an existing (possibly reviewed) entry is never overwritten."""
    if not items:
        return
    now = datetime.now(timezone.utc)
    operations = [
        UpdateOne(
            {"name": item["name"], "category": category},
            {"$setOnInsert": {**item, "category": category, "model": model, "reviewed": False, "created_at": now}},
            upsert=True,
        )
        for item in items
    ]
    await get_database().ai_explanations.bulk_write(operations, ordered=False)
