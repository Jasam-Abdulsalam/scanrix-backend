from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.schemas.product import ScanRequest, ScanResponse, AnalyzeTextRequest
from app.api.deps import get_current_user, check_rate_limit
from app.crud.crud_product import get_product_by_barcode, create_product, update_product_analysis
from app.crud.crud_history import create_history
from app.services.openfoodfacts_service import openfoodfacts_service
from app.services.openbeautyfacts_service import openbeautyfacts_service
from app.services.ai_service import ai_service
from app.models.product import product_helper
import asyncio



router = APIRouter()

@router.post("/", response_model=ScanResponse)
async def scan_product(
    scan_request: ScanRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(check_rate_limit)
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
    
    # 2. Not in database - Run Parallel Search (The Asynchronous Race)
    # Fire off requests to both databases simultaneously
    results = await asyncio.gather(
        openfoodfacts_service.get_product(barcode),
        openbeautyfacts_service.get_product(barcode),
        return_exceptions=True
    )
    
    product_data = None
    for res in results:
        # Check if the result is a valid dict (ignores Exceptions and Nones)
        if isinstance(res, dict) and res.get("barcode"):
            product_data = res
            print(f"🎯 Product found in {product_data.get('source')} database!")
            break
    
    if product_data:
        # Found in Open Food Facts
        # Set initial processing status
        product_data["verdict"] = "analyzing"
        product_data["overall_score"] = None
        
        # Save to database immediately so the user gets an instant response
        new_product = await create_product(product_data)
        
        # Extract ingredients text for AI
        ingredients_text = ", ".join([ing["name"] for ing in product_data.get("ingredients", [])])
        
        # Run AI analysis in the background
        if ingredients_text:
            background_tasks.add_task(
                run_ai_analysis_background,
                str(new_product["_id"]),
                ingredients_text,
                product_data["category"]
            )
        else:
            # No ingredients to analyze, just mark as safe/unknown
            await update_product_analysis(str(new_product["_id"]), {
                "overall_score": 50,
                "verdict": "unknown",
                "ingredients": []
            })
        
        # Save to history
        await create_history(
            user_id=str(current_user["_id"]),
            product_id=str(new_product["_id"]),
            verdict="analyzing"
        )
        
        return {
            "product": product_helper(new_product),
            "personalized_score": None,
            "concerns_for_user": []
        }
    
    # 3. Not found anywhere
    raise HTTPException(status_code=404, detail="Product not found in any database")

async def run_ai_analysis_background(product_id: str, ingredients_text: str, category: str):
    """Background task to fetch AI analysis and update the database"""
    print(f"🔄 Starting background AI analysis for product {product_id}")
    try:
        # This function handles its own rate limits and caching internally now!
        ai_analysis = await ai_service.analyze_ingredients(
            ingredients_text,
            category
        )
        
        if ai_analysis:
            # Update the product in MongoDB
            await update_product_analysis(product_id, ai_analysis)
            print(f"✅ Background AI analysis complete for product {product_id}")
        else:
            print(f"⚠️ Background AI analysis returned empty for {product_id}")
            # Mark it as failed/unknown so mobile app knows to stop polling
            await update_product_analysis(product_id, {
                "overall_score": 50,
                "verdict": "unknown"
            })
            
    except Exception as e:
        print(f"❌ Background task error: {e}")
        await update_product_analysis(product_id, {
            "overall_score": 50,
            "verdict": "error"
        })

@router.post("/analyze-text")
async def analyze_text(
    request: AnalyzeTextRequest,
    current_user = Depends(check_rate_limit)
):
    """
    Directly analyze raw ingredient text from OCR without a barcode.
    This bypasses open food/beauty facts and hits the AI directly.
    """
    if not request.ingredients_text or len(request.ingredients_text.strip()) < 5:
        raise HTTPException(
            status_code=400, 
            detail="Ingredients list is too short or empty. Please ensure the OCR scan worked correctly."
        )
        
    print(f"📝 Starting OCR text analysis for category '{request.category}'")
    
    try:
        # Await the AI instantly since there's no DB background logic to perform first
        ai_analysis = await ai_service.analyze_ingredients(
            request.ingredients_text,
            request.category
        )
        
        if ai_analysis:
            return {
                "success": True,
                "analysis": ai_analysis
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail="AI failed to generate a valid analysis."
            )
            
    except Exception as e:
        print(f"❌ Text analyze error: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while analyzing the text.")