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
