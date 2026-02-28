from fastapi import APIRouter, Depends, HTTPException
from app.schemas.product import ScanRequest, ScanResponse
from app.api.deps import get_current_user
from app.crud.crud_product import get_product_by_barcode, create_product
from app.crud.crud_history import create_history
from app.services.openfoodfacts_service import openfoodfacts_service
from app.services.gemini_service import gemini_service
from app.models.product import product_helper



router = APIRouter()

@router.post("/", response_model=ScanResponse)
async def scan_product(
    scan_request: ScanRequest,
    current_user = Depends(get_current_user)
):
    """Scan a product by barcode"""
    if not scan_request.barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")
    
    barcode = scan_request.barcode
    
    # 1. Check if product exists in our database
    product = await get_product_by_barcode(barcode)
    
    if product:
        # Product found - save to history and return
        await create_history(
            user_id=str(current_user["_id"]),
            product_id=str(product["_id"]),
            verdict=product.get("verdict", "unknown")
        )
        return {
            "product": product_helper(product),
            "personalized_score": None,
            "concerns_for_user": []
        }
    
    # 2. Not in database - try Open Food Facts
    product_data = await openfoodfacts_service.get_product(barcode)
    
    if product_data:
        # Found in Open Food Facts
        # Enhance with Gemini analysis
        ingredients_text = ", ".join([ing["name"] for ing in product_data["ingredients"]])
        gemini_analysis = await gemini_service.analyze_ingredients(
            ingredients_text,
            product_data["category"]
        )
        
        if gemini_analysis:
            product_data["overall_score"] = gemini_analysis.get("overall_score", 50)
            product_data["verdict"] = gemini_analysis.get("verdict", "unknown")
            product_data["ingredients"] = gemini_analysis.get("ingredients", product_data["ingredients"])
        
        # Save to database
        new_product = await create_product(product_data)
        
        # Save to history
        await create_history(
            user_id=str(current_user["_id"]),
            product_id=str(new_product["_id"]),
            verdict=new_product.get("verdict", "unknown")
        )
        
        return {
            "product": product_helper(new_product),
            "personalized_score": None,
            "concerns_for_user": []
        }
    
    # 3. Not found anywhere
    raise HTTPException(status_code=404, detail="Product not found in any database")