from fastapi import APIRouter, Depends, HTTPException
from app.schemas.product import ProductDetailResponse
from app.crud.crud_product import get_product_by_barcode, get_product_by_id
from app.api.deps import get_current_user
from app.models.product import product_helper
from app.services.ingredient_db_service import ingredient_db_service
from app.services.ai_product_service import cached_analysis_for_product


router = APIRouter()

@router.get("/{barcode}", response_model=ProductDetailResponse)
async def get_product(
    barcode: str,
    current_user = Depends(get_current_user)
):
    """Get product by barcode"""
    product = await get_product_by_barcode(barcode)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    evaluation = await ingredient_db_service.evaluate_product_ingredients(
        product.get("ingredients", []),
        category=product.get("category", "food")
    )
    result = ingredient_db_service.overlay_legacy_fields(product_helper(product), evaluation)
    return {**result, "safety_engine": evaluation, "ai_analysis": await cached_analysis_for_product(product)}