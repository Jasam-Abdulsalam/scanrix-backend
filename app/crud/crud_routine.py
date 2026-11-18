"""One document per user: {user_id, morning: [item], evening: [item], product_types: {barcode: type}, created_at,
updated_at}, where an item is {product_id, barcode, added_at}. Array order = step order. product_types holds the
user's label per product (shared by both slots), only for products in a slot. Unique index on user_id
(app/db/indexes.py). Barcodes match BARCODE_PATTERN (letters, digits, '-'), so they are safe as field names."""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from bson import ObjectId

from app.db.mongodb import get_database


class AddResult(Enum):
    ADDED = "added"
    ALREADY_THERE = "already_there"
    FULL = "full"


async def get_routine(user_id: str) -> Optional[dict]:
    return await get_database().routines.find_one({"user_id": ObjectId(user_id)})


async def _ensure_doc(user_id: str) -> None:
    """Create the user's empty routine if missing. Upsert on the unique user_id: a race creates one doc."""
    now = datetime.now(timezone.utc)
    await get_database().routines.update_one(
        {"user_id": ObjectId(user_id)},
        {"$setOnInsert": {"morning": [], "evening": [], "created_at": now, "updated_at": now}},
        upsert=True,
    )


async def add_item(user_id: str, slot: str, product_id: ObjectId, barcode: str, max_items: int) -> AddResult:
    """Atomic check-and-push: the filter only matches when the barcode is not in the slot yet AND the slot has
    room (no element at index max_items-1), so two concurrent adds can't duplicate or overfill."""
    await _ensure_doc(user_id)
    db = get_database()
    now = datetime.now(timezone.utc)
    result = await db.routines.update_one(
        {"user_id": ObjectId(user_id), f"{slot}.barcode": {"$ne": barcode}, f"{slot}.{max_items - 1}": {"$exists": False}},
        {"$push": {slot: {"product_id": product_id, "barcode": barcode, "added_at": now}}, "$set": {"updated_at": now}},
    )
    if result.modified_count == 1:
        return AddResult.ADDED
    doc = await get_routine(user_id)
    in_slot = any(i.get("barcode") == barcode for i in (doc or {}).get(slot, []))
    return AddResult.ALREADY_THERE if in_slot else AddResult.FULL


async def remove_item(user_id: str, slot: str, barcode: str) -> None:
    """Idempotent: not there = nothing to do. Once the product is in neither slot, its type is dropped too
    (guarded by the filter, so a concurrent re-add keeps it)."""
    db = get_database()
    await db.routines.update_one(
        {"user_id": ObjectId(user_id)},
        {"$pull": {slot: {"barcode": barcode}}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    await db.routines.update_one(
        {"user_id": ObjectId(user_id), "morning.barcode": {"$ne": barcode}, "evening.barcode": {"$ne": barcode}},
        {"$unset": {f"product_types.{barcode}": ""}},
    )


async def set_product_type(user_id: str, barcode: str, product_type: Optional[str]) -> bool:
    """Set (or clear, when None) the product's type. Only while the product is in a slot: False otherwise."""
    now = datetime.now(timezone.utc)
    field = f"product_types.{barcode}"
    update = {"$set": {field: product_type, "updated_at": now}} if product_type else \
        {"$unset": {field: ""}, "$set": {"updated_at": now}}
    result = await get_database().routines.update_one(
        {"user_id": ObjectId(user_id), "$or": [{"morning.barcode": barcode}, {"evening.barcode": barcode}]},
        update,
    )
    return result.matched_count == 1


async def set_order(user_id: str, slot: str, items: List[dict]) -> bool:
    """Replace the slot with the same items in a new order. Only applies if the slot still holds exactly
    these barcodes ($all + $size), so a concurrent add/remove makes this fail instead of losing a change."""
    barcodes = [i["barcode"] for i in items]
    result = await get_database().routines.update_one(
        {"user_id": ObjectId(user_id), f"{slot}.barcode": {"$all": barcodes}, slot: {"$size": len(barcodes)}},
        {"$set": {slot: items, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.matched_count == 1


async def delete_user_routine(user_id: str) -> int:
    """Account deletion cascade."""
    result = await get_database().routines.delete_many({"user_id": ObjectId(user_id)})
    return result.deleted_count
