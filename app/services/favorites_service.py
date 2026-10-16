from typing import List, Optional

from app.core.config import settings
from app.core.pagination import split_page
from app.crud import crud_favorites, crud_product
from app.models.product import product_helper
from app.schemas.favorites import FavoriteRead


class ProductNotFound(Exception):
    pass


class FavoritesLimitReached(Exception):
    pass


async def add(user_id: str, barcode: str) -> None:
    """Save a product. Already saved = no-op (also at the cap). The cap is checked before the insert,
    so two simultaneous adds by one user can overshoot it by one: acceptable for an abuse guard."""
    product = await crud_product.get_product_by_barcode(barcode)
    if product is None:
        raise ProductNotFound()
    if await crud_favorites.is_favorite(user_id, product["_id"]):
        return
    if await crud_favorites.count_favorites(user_id) >= settings.FAVORITES_MAX_PER_USER:
        raise FavoritesLimitReached()
    await crud_favorites.add_favorite(user_id, product["_id"], barcode)


async def remove(user_id: str, barcode: str) -> None:
    await crud_favorites.remove_favorite(user_id, barcode)  # idempotent: not saved = nothing to do


async def barcodes(user_id: str) -> List[str]:
    return await crud_favorites.favorite_barcodes(user_id, settings.FAVORITES_MAX_PER_USER + 50)


async def list_page(user_id: str, limit: int, cursor: Optional[str] = None) -> dict:
    """One page, newest saved first. Two queries per page (favorites + one batched `$in`).
    A saved product that no longer exists is left out, so a page can hold fewer than `limit` rows."""
    fetched = await crud_favorites.list_favorites(user_id, limit, cursor)
    rows, next_cursor = split_page(fetched, limit, "created_at")
    products = await crud_product.get_products_by_ids([str(r["product_id"]) for r in rows])
    by_id = {str(p["_id"]): product_helper(p) for p in products}
    items = [_read(row, by_id[str(row["product_id"])]) for row in rows if str(row["product_id"]) in by_id]
    return {"items": items, "next_cursor": next_cursor, "has_more": next_cursor is not None}


def _read(row: dict, p: dict) -> dict:
    return FavoriteRead(
        id=str(row["_id"]), barcode=p["barcode"], name=p["name"], brand=p["brand"], category=p["category"],
        image_url=p["image_url"], verdict=p["verdict"], overall_score=p["overall_score"],
        added_at=row["created_at"],
    ).model_dump()
