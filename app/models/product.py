from datetime import datetime
from typing import Optional

def product_helper(product) -> dict:
    """Convert MongoDB product document to dict"""
    return {
        "id": str(product["_id"]),
        "barcode": product["barcode"],
        "name": product["name"],
        "brand": product["brand"],
        "category": product["category"],
        "ingredients": product.get("ingredients", []),
        "overall_score": product.get("overall_score", 0),
        "verdict": product.get("verdict", "unknown"),
        "image_url": product.get("image_url"),
        "source": product.get("source", "manual"),
        "created_at": product.get("created_at", datetime.utcnow()),
    }