from typing import Optional

from app.crud import crud_history, crud_product
from app.models.history import history_helper
from app.models.product import product_helper
from app.schemas.history import HistoryProduct
from app.core.pagination import split_page


async def list_history(user_id: str, limit: int, cursor: Optional[str] = None) -> dict:
    """One page, newest first, each entry with a small product summary.
    Two queries per page (history + one batched `$in` for the products), not one per row."""
    fetched = await crud_history.get_user_history(user_id, limit, cursor)
    entries, next_cursor = split_page(fetched, limit, "scanned_at")
    products = await crud_product.get_products_by_ids([str(e["product_id"]) for e in entries])
    summaries = {str(p["_id"]): _summary(p) for p in products}
    items = [{**history_helper(e), "product": summaries.get(str(e["product_id"]))} for e in entries]
    return {"items": items, "next_cursor": next_cursor, "has_more": next_cursor is not None}


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


async def count_history(user_id: str) -> dict:
    return {"count": await crud_history.count_user_history(user_id)}
