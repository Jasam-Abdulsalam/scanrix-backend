"""My Routine: a user's morning and evening cosmetics, in step order (API_CONTRACT.md section 16)."""
from typing import Dict, List, Optional

from app.core.config import settings
from app.crud import crud_product, crud_routine
from app.crud.crud_routine import AddResult
from app.schemas.routine import RoutineItemRead, RoutineRead

SLOTS = ("morning", "evening")


class ProductNotFound(Exception):
    pass


class NotCosmetic(Exception):
    """Routines are for cosmetics only."""


class RoutineSlotFull(Exception):
    pass


class NotInRoutine(Exception):
    """A product type can only be set for a product that is in a slot."""


class OrderMismatch(Exception):
    """The new order doesn't hold exactly the slot's current products (stale screen or concurrent change)."""


async def get(user_id: str) -> RoutineRead:
    """Two queries: the routine doc + one batched `$in` for every product in both slots. A product that no
    longer exists is left out (like saved products)."""
    doc = await crud_routine.get_routine(user_id) or {}
    items = {slot: doc.get(slot, []) for slot in SLOTS}
    ids = [str(i["product_id"]) for slot in SLOTS for i in items[slot]]
    products = {str(p["_id"]): p for p in await crud_product.get_products_by_ids(ids)}
    types = doc.get("product_types") or {}
    return RoutineRead(**{slot: _read(items[slot], products, types) for slot in SLOTS})


def _read(items: List[dict], products: Dict[str, dict], types: Dict[str, str]) -> List[RoutineItemRead]:
    out = []
    for item in items:
        p = products.get(str(item["product_id"]))
        if p is None:
            continue
        out.append(RoutineItemRead(
            barcode=p["barcode"], name=p["name"], brand=p.get("brand"), image_url=p.get("image_url"),
            verdict=p.get("verdict"), overall_score=p.get("overall_score"),
            product_type=types.get(item["barcode"]), added_at=item["added_at"],
        ))
    return out


async def add(user_id: str, slot: str, barcode: str) -> None:
    """Add as the last step. Already in this slot = no-op (safe to repeat)."""
    product = await crud_product.get_product_by_barcode(barcode)
    if product is None:
        raise ProductNotFound()
    if product.get("category") != "cosmetic":
        raise NotCosmetic()
    result = await crud_routine.add_item(user_id, slot, product["_id"], barcode, settings.ROUTINE_MAX_PER_SLOT)
    if result is AddResult.FULL:
        raise RoutineSlotFull()


async def set_product_type(user_id: str, barcode: str, product_type: Optional[str]) -> None:
    """Label a product in the routine (both slots share it). None clears it."""
    if not await crud_routine.set_product_type(user_id, barcode, product_type):
        raise NotInRoutine()


async def remove(user_id: str, slot: str, barcode: str) -> None:
    await crud_routine.remove_item(user_id, slot, barcode)


async def reorder(user_id: str, slot: str, barcodes: List[str]) -> None:
    """`barcodes` must be exactly the slot's products (no missing, extra or repeated ones)."""
    doc = await crud_routine.get_routine(user_id) or {}
    current = {i["barcode"]: i for i in doc.get(slot, [])}
    if len(barcodes) != len(set(barcodes)) or set(barcodes) != set(current):
        raise OrderMismatch()
    if not await crud_routine.set_order(user_id, slot, [current[b] for b in barcodes]):
        raise OrderMismatch()  # the slot changed between our read and the write
