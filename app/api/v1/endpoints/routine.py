from fastapi import APIRouter, Depends, HTTPException, Path, Response, status

from app.api.deps import get_current_user
from app.schemas.routine import BARCODE_PATTERN, ProductTypeRequest, RoutineOrderRequest, RoutineRead, Slot
from app.services import routine_service as service

router = APIRouter()

BarcodePath = Path(..., min_length=4, max_length=64, pattern=BARCODE_PATTERN)


@router.get("/", response_model=RoutineRead)
async def get_routine(current_user=Depends(get_current_user)):
    """The user's morning and evening products, in step order (bounded: each slot is capped)."""
    return await service.get(str(current_user["_id"]))


# Declared before PUT /{slot}/{barcode}: both are two path segments, and FastAPI uses the first match.
@router.put("/product-type/{barcode}", status_code=status.HTTP_204_NO_CONTENT)
async def set_product_type(body: ProductTypeRequest, barcode: str = BarcodePath, current_user=Depends(get_current_user)):
    """Set the product's type (cleanser, toner, serum, moisturizer, sunscreen, other; null clears it). Shared by
    both slots. 404 `not_in_routine` unless the product is in a slot."""
    try:
        await service.set_product_type(str(current_user["_id"]), barcode, body.product_type)
    except service.NotInRoutine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "not_in_routine", "message": "Add this product to your routine first."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{slot}/{barcode}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_routine(slot: Slot, barcode: str = BarcodePath, current_user=Depends(get_current_user)):
    """Add a cosmetic as the slot's last step. Safe to repeat. 404 unknown barcode, 422 `not_cosmetic`,
    409 `routine_slot_full`."""
    try:
        await service.add(str(current_user["_id"]), slot, barcode)
    except service.ProductNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    except service.NotCosmetic:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "not_cosmetic", "message": "Only cosmetics can be added to a routine."})
    except service.RoutineSlotFull:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "routine_slot_full", "message": "This routine is full. Remove a step first."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{slot}/{barcode}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_routine(slot: Slot, barcode: str = BarcodePath, current_user=Depends(get_current_user)):
    """Remove a step. Safe to repeat (204 even if it was not there)."""
    await service.remove(str(current_user["_id"]), slot, barcode)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{slot}", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_routine(slot: Slot, body: RoutineOrderRequest, current_user=Depends(get_current_user)):
    """Set the slot's step order. 422 `order_mismatch` unless `barcodes` is exactly the slot's products."""
    try:
        await service.reorder(str(current_user["_id"]), slot, body.barcodes)
    except service.OrderMismatch:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "order_mismatch", "message": "Your routine changed. Reload it and try again."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
