from fastapi import APIRouter, Depends, HTTPException
from app.schemas.product import ProductResponse
from app.crud.crud_product import get_product_by_barcode, get_product_by_id
from app.api.deps import get_current_user
from app.models.product import product_helper


router = APIRouter()

@router.get("/{barcode}", response_model=ProductResponse)
async def get_product(
    barcode: str,
    current_user = Depends(get_current_user)
):
    """Get product by barcode"""
    product = await get_product_by_barcode(barcode)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product_helper(product)