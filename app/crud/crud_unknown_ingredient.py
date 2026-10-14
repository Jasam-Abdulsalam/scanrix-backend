from datetime import datetime, timezone
from typing import Iterable, List, Optional

from pymongo import UpdateOne

from app.db.mongodb import get_database

MAX_NAME_LENGTH = 80       # OCR noise longer than this is not an ingredient name
VALID_CATEGORIES = {"food", "cosmetic", "household"}
MAX_NAMES_PER_SCAN = 100   # bounds the write size of one scan


def clean_unknown_names(names: Iterable[str]) -> List[str]:
    """Lower-cased, de-duplicated, length-bounded names. Pure: easy to test."""
    seen = dict.fromkeys(
        n.strip().lower() for n in names if isinstance(n, str) and 0 < len(n.strip()) <= MAX_NAME_LENGTH
    )
    return list(seen)[:MAX_NAMES_PER_SCAN]


async def record_unknown_ingredients(
    names: Iterable[str], category: str, example_barcode: Optional[str] = None
) -> int:
    """
    Adds 1 to the scan counter of every unrecognised ingredient name (one atomic upsert each,
    all sent in a single bulk write, so concurrent scans never lose a count).
    Stores no user data. Returns how many names were recorded.
    """
    cleaned = clean_unknown_names(names)
    if not cleaned or category not in VALID_CATEGORIES:  # client-supplied category must not create junk rows
        return 0
    now = datetime.now(timezone.utc)
    operations = [
        UpdateOne(
            {"name": name, "category": category},
            {
                "$inc": {"scan_count": 1},
                "$set": {"last_seen": now},
                "$setOnInsert": {"first_seen": now, "example_barcode": example_barcode},
            },
            upsert=True,
        )
        for name in cleaned
    ]
    await get_database().unknown_ingredients.bulk_write(operations, ordered=False)
    return len(cleaned)


async def top_unknown_ingredients(limit: int = 50, category: Optional[str] = None) -> List[dict]:
    """Most-scanned unrecognised names first (served by the scan_count index)."""
    query = {"category": category} if category else {}
    cursor = get_database().unknown_ingredients.find(query, {"_id": 0}).sort("scan_count", -1).limit(limit)
    return await cursor.to_list(length=limit)
