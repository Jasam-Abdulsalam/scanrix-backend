from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursor
from app.schemas.favorites import FavoriteBarcodes, FavoritePage
from app.services import favorites_service as service

router = APIRouter()


@router.get("/", response_model=FavoritePage)
async def list_favorites(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: Optional[str] = Query(None, max_length=256),
    current_user=Depends(get_current_user),
):
    """Saved products, newest saved first, one page at a time (cursor pagination)."""
    try:
        return await service.list_page(str(current_user["_id"]), limit, cursor)
    except InvalidCursor:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "invalid_cursor", "message": "The page cursor is not valid. Reload the list."})


@router.get("/barcodes", response_model=FavoriteBarcodes)
async def favorite_barcodes(current_user=Depends(get_current_user)):
    """Every saved barcode (bounded by the per-user cap), so the app can fill its hearts in one call."""
    return {"barcodes": await service.barcodes(str(current_user["_id"]))}


@router.put("/{barcode}", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(barcode: str, current_user=Depends(get_current_user)):
    """Save a product. Safe to repeat. 404 unknown barcode, 409 `favorites_limit_reached`."""
    try:
        await service.add(str(current_user["_id"]), barcode)
    except service.ProductNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    except service.FavoritesLimitReached:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "favorites_limit_reached", "message": "You have reached the limit of saved products."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{barcode}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(barcode: str, current_user=Depends(get_current_user)):
    """Un-save a product. Safe to repeat (204 even if it was not saved)."""
    await service.remove(str(current_user["_id"]), barcode)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
