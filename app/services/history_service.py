from typing import List

from app.crud import crud_history, crud_product
from app.models.history import history_helper
from app.models.product import product_helper
from app.schemas.history import HistoryProduct


async def list_history(user_id: str, limit: int) -> List[dict]:
    """Newest first, each entry with a small product summary.
    Two queries total (history + one batched `$in` for the products), not one per row."""
    entries = await crud_history.get_user_history(user_id, limit)
    products = await crud_product.get_products_by_ids([str(e["product_id"]) for e in entries])
    summaries = {str(p["_id"]): _summary(p) for p in products}
    return [{**history_helper(e), "product": summaries.get(str(e["product_id"]))} for e in entries]


def _summary(product: dict) -> dict:
    p = product_helper(product)
    return HistoryProduct(
        barcode=p["barcode"], name=p["name"], brand=p["brand"],
        category=p["category"], image_url=p["image_url"],
    ).model_dump()


async def delete_entry(user_id: str, history_id: str) -> bool:
    return await crud_history.delete_history_entry(user_id, history_id)


async def clear_history(user_id: str) -> int:
    return await crud_history.delete_user_history(user_id)
