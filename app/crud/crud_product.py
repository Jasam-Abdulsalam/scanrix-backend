from bson import ObjectId
from app.db.mongodb import get_database
from datetime import datetime


async def create_product(product_data: dict):
    """Create a new product"""
    db = get_database()
    product_data["created_at"] = datetime.utcnow()
    result = await db.products.insert_one(product_data)
    product_data["_id"] = result.inserted_id
    return product_data

async def get_product_by_barcode(barcode: str):
    """Get product by barcode"""
    db = get_database()
    product = await db.products.find_one({"barcode": barcode})
    return product

async def get_product_by_id(product_id: str):
    """Get product by ID"""
    db = get_database()
    product = await db.products.find_one({"_id": ObjectId(product_id)})
    return product

async def get_products_by_ids(product_ids: list) -> list:
    """Batch lookup (one `$in` query, never one query per id). Unknown/invalid ids are skipped."""
    object_ids = [ObjectId(i) for i in set(product_ids) if ObjectId.is_valid(i)]
    if not object_ids:
        return []
    db = get_database()
    return await db.products.find({"_id": {"$in": object_ids}}).to_list(length=len(object_ids))


async def set_mirrored_image(barcode: str, source_url: str, mirrored_url: str) -> bool:
    """Points the product at its Cloudinary copy, keeping the original in `image_source_url`.
    Only when `image_url` is still `source_url` (atomic: a concurrent change wins). True if saved."""
    db = get_database()
    result = await db.products.update_one(
        {"barcode": barcode, "image_url": source_url},
        {"$set": {"image_url": mirrored_url, "image_source_url": source_url}},
    )
    return result.modified_count == 1


async def products_needing_image_mirror(limit: int) -> list:
    """Barcode + image_url of products whose https photo hasn't been copied yet (no image_source_url).
    Small one-off backfill query on `products` (bounded by limit), so no dedicated index."""
    db = get_database()
    cursor = db.products.find(
        {"image_url": {"$regex": "^https://"}, "image_source_url": {"$exists": False}},
        {"_id": 0, "barcode": 1, "image_url": 1},
    ).limit(limit)
    return await cursor.to_list(length=limit)
