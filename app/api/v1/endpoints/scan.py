from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.schemas.product import ScanRequest, ScanResponse, AnalyzeTextRequest
from app.api.deps import get_current_user, check_rate_limit
from app.crud.crud_product import get_product_by_barcode, create_product, update_product_analysis
from app.crud.crud_history import create_history
from app.services.openfoodfacts_service import openfoodfacts_service
from app.services.openbeautyfacts_service import openbeautyfacts_service
from app.services.ai_service import ai_service
from app.services.ingredient_db_service import ingredient_db_service
from app.models.product import product_helper
import asyncio

router = APIRouter()

@router.post("/", response_model=ScanResponse)
async def scan_product(
    scan_request: ScanRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(check_rate_limit)
):
    """Scan a product by barcode using Database-First Ingredient Engine"""
    if not scan_request.barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")
    
    barcode = scan_request.barcode
    
    # 1. Check if product already exists in our database
    product = await get_product_by_barcode(barcode)
    
    if product:
        # Re-evaluate with latest ruleset and verified facts
        ingredients_list = product.get("ingredients", [])
        ingredients_text = ", ".join([ing.get("name", "") for ing in ingredients_list if isinstance(ing, dict)])
        
        evaluation = None
        if ingredients_text:
            evaluation, _ = await ingredient_db_service.analyze_ingredients_text(
                ingredients_text,
                category=product.get("category", "food")
            )

        # Save to scan history
        await create_history(
            user_id=str(current_user["_id"]),
            product_id=str(product["_id"]),
            verdict=product.get("verdict", "unknown")
        )
        return {
            "product": product_helper(product),
            "personalized_score": None,
            "concerns_for_user": [],
            "safety_engine": evaluation
        }
    
    # 2. Not in database - Fetch from Open Food Facts / Open Beauty Facts
    results = await asyncio.gather(
        openfoodfacts_service.get_product(barcode),
        openbeautyfacts_service.get_product(barcode),
        return_exceptions=True
    )
    
    product_data = None
    for res in results:
        if isinstance(res, dict) and res.get("barcode"):
            product_data = res
            print(f"🎯 Product found in {product_data.get('source')} database!")
            break
    
    if product_data:
        # Extract ingredients text from product payload
        ingredients_list = product_data.get("ingredients", [])
        ingredients_text = ", ".join([ing.get("name", "") for ing in ingredients_list if isinstance(ing, dict)])

        evaluation = None
        unknown_ingredients = []

        if ingredients_text:
            # 3. Database-First Safety Evaluation
            evaluation, unknown_ingredients = await ingredient_db_service.analyze_ingredients_text(
                ingredients_text,
                category=product_data.get("category", "food")
            )
            # Compute deterministic score & verdict
            verdict, score, summary = ingredient_db_service.calculate_legacy_verdict_and_score(evaluation)
            product_data["verdict"] = verdict
            product_data["overall_score"] = score
            product_data["summary"] = summary
        else:
            product_data["verdict"] = "unknown"
            product_data["overall_score"] = 50
            product_data["summary"] = "No ingredient text available on packaging."

        # Save product in MongoDB
        new_product = await create_product(product_data)
        product_id = str(new_product["_id"])

        # 4. Trigger AI fallback ONLY for unknown ingredients (if any remain)
        if unknown_ingredients:
            print(f"🤖 Queuing {len(unknown_ingredients)} unrecognised ingredients for AI fallback: {unknown_ingredients}")
            background_tasks.add_task(
                run_ai_fallback_background,
                product_id,
                ", ".join(unknown_ingredients),
                product_data.get("category", "food")
            )
        else:
            print("✨ 100% ingredients recognised in verified database — zero AI calls needed!")

        # Save to history
        await create_history(
            user_id=str(current_user["_id"]),
            product_id=product_id,
            verdict=product_data["verdict"]
        )
        
        return {
            "product": product_helper(new_product),
            "personalized_score": None,
            "concerns_for_user": [],
            "safety_engine": evaluation
        }
    
    # 3. Not found in Open Food Facts / Open Beauty Facts
    raise HTTPException(status_code=404, detail="Product not found in any database")

from app.services.ai_fallback_service import ai_fallback_service

async def run_ai_fallback_background(product_id: str, unknown_ingredients_text: str, category: str):
    """
    Fallback worker: only invoked for unrecognised ingredients.
    Saves AI proposals in ai_review_queue and stores them as Tier 4 unverified facts.
    """
    print(f"🔄 Starting background AI fallback for product {product_id} (unknowns: {unknown_ingredients_text})")
    try:
        # 1. Process each unknown ingredient into the AI review queue and Tier 4 facts
        unknowns = [i.strip() for i in unknown_ingredients_text.split(",") if i.strip()]
        for unknown in unknowns:
            await ai_fallback_service.process_unknown_ingredient(unknown, category)

        # 2. Also run legacy product update for older mobile clients
        ai_analysis = await ai_service.analyze_ingredients(
            unknown_ingredients_text,
            category
        )
        if ai_analysis:
            await update_product_analysis(product_id, ai_analysis)
            print(f"✅ AI fallback completed for product {product_id}")
    except Exception as e:
        print(f"❌ Background AI fallback error: {e}")

@router.post("/analyze-text")
async def analyze_text(
    request: AnalyzeTextRequest,
    current_user = Depends(check_rate_limit)
):
    """
    Directly analyze raw ingredient text from OCR using the Database Safety Engine.
    Fast, deterministic, and returns multi-dimensional risk + coverage.
    """
    if not request.ingredients_text or len(request.ingredients_text.strip()) < 5:
        raise HTTPException(
            status_code=400, 
            detail="Ingredients list is too short or empty. Please ensure the OCR scan worked correctly."
        )
        
    print(f"📝 Starting OCR text analysis for category '{request.category}'")
    
    try:
        # Run database safety engine
        evaluation, unknown_ingredients = await ingredient_db_service.analyze_ingredients_text(
            request.ingredients_text,
            category=request.category
        )
        
        verdict, score, summary = ingredient_db_service.calculate_legacy_verdict_and_score(evaluation)
        
        return {
            "success": True,
            "verdict": verdict,
            "overall_score": score,
            "summary": summary,
            "safety_engine": evaluation,
            "unknown_ingredients": unknown_ingredients
        }
    except Exception as e:
        print(f"❌ Text analyze error: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while analyzing the text.")