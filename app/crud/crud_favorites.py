from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.core.pagination import after_cursor_filter, newest_first
from app.db.mongodb import get_database


async def is_favorite(user_id: str, product_id: ObjectId) -> bool:
    db = get_database()
    return await db.favorites.find_one({"user_id": ObjectId(user_id), "product_id": product_id}, {"_id": 1}) is not None


async def count_favorites(user_id: str) -> int:
    db = get_database()
    return await db.favorites.count_documents({"user_id": ObjectId(user_id)})


async def add_favorite(user_id: str, product_id: ObjectId, barcode: str) -> None:
    """Idempotent: the unique (user_id, product_id) index + upsert means a repeat or a race adds nothing.
    `barcode` is stored with the row so the app's "which barcodes are saved" call needs no join."""
    db = get_database()
    await db.favorites.update_one(
        {"user_id": ObjectId(user_id), "product_id": product_id},
        {"$setOnInsert": {"barcode": barcode, "created_at": datetime.utcnow()}},
        upsert=True,
    )


async def remove_favorite(user_id: str, barcode: str) -> None:
    db = get_database()
    await db.favorites.delete_one({"user_id": ObjectId(user_id), "barcode": barcode})


async def list_favorites(user_id: str, limit: int, cursor: Optional[str] = None) -> List[dict]:
    """One page, newest first; fetches limit + 1 (the extra row only says "there is more").
    Raises pagination.InvalidCursor for a cursor we did not issue."""
    db = get_database()
    query = {"user_id": ObjectId(user_id), **after_cursor_filter("created_at", cursor)}
    return await db.favorites.find(query).sort(newest_first("created_at")).limit(limit + 1).to_list(length=limit + 1)


async def favorite_barcodes(user_id: str, max_items: int) -> List[str]:
    db = get_database()
    rows = await db.favorites.find({"user_id": ObjectId(user_id)}, {"barcode": 1}).to_list(length=max_items)
    return [r["barcode"] for r in rows]


async def delete_user_favorites(user_id: str) -> int:
    """Account deletion cascade."""
    db = get_database()
    result = await db.favorites.delete_many({"user_id": ObjectId(user_id)})
    return result.deleted_count
