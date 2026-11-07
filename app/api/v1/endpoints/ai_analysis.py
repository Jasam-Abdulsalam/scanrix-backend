import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.ai_alternatives import AIAlternativesRequest, AIAlternativesResponse
from app.schemas.ai_analysis import AIAnalyzeRequest, AIAnalyzeResponse, CreditsResponse
from app.schemas.ai_natural_remedy import AINaturalRemedyResponse, NaturalRemedyRequest
from app.services import ai_alternatives_service, ai_natural_remedy_service
from app.services import ai_product_service as ai
from app.services import credits_service
from app.services.credits_service import CreditsExhausted

router = APIRouter()


def _credits_exhausted(e: CreditsExhausted) -> HTTPException:
    wait = max(math.ceil((e.resets_at - datetime.now(timezone.utc)).total_seconds()), 1)
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait)}, detail={
        "code": "ai_credits_exhausted", "message": "You have used all AI credits for this week.",
        "resets_at": e.resets_at.isoformat()})


def _ai_unavailable() -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
        "code": "ai_unavailable", "message": "AI analysis is not available right now. You were not charged. Please try again later."})


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(current_user=Depends(get_current_user)):
    """AI credits left this week (shared by 'Get AI verdict' and future AI features)."""
    balance = await credits_service.get_balance(str(current_user["_id"]))
    return CreditsResponse(limit=balance.limit, remaining=balance.remaining, resets_at=balance.resets_at)


@router.post("/analyze-product", response_model=AIAnalyzeResponse)
async def analyze_product(request: AIAnalyzeRequest, current_user=Depends(get_current_user)):
    """
    Opt-in "Get AI verdict" for a product our database cannot judge well. Costs 1 credit unless the
    answer already exists. The result is an UNVERIFIED estimate shown beside (never replacing) the
    database verdict.
    """
    try:
        return await ai.analyze_product(str(current_user["_id"]), request)
    except ai.ProductNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    except ai.IngredientsMissingError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "ingredients_missing", "message": "No ingredient list to analyse. Scan the ingredients label first."})
    except CreditsExhausted as e:
        raise _credits_exhausted(e)
    except ai.AIUnavailableError:
        raise _ai_unavailable()


@router.post("/alternatives", response_model=AIAlternativesResponse)
async def get_alternatives(request: AIAlternativesRequest, current_user=Depends(get_current_user)):
    """
    AI-suggested alternatives for a scanned product (same type, sold in India, similar price, avoiding
    the ingredients our database flagged). Costs 1 credit unless an answer for this product already
    exists. UNVERIFIED suggestions: names, prices and ingredients come from the AI.
    """
    try:
        return await ai_alternatives_service.get_alternatives(str(current_user["_id"]), request.barcode)
    except ai.ProductNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    except ai.IngredientsMissingError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "ingredients_missing", "message": "No ingredient list for this product. Scan the ingredients label first."})
    except CreditsExhausted as e:
        raise _credits_exhausted(e)
    except ai.AIUnavailableError:
        raise _ai_unavailable()


@router.post("/natural-remedy", response_model=AINaturalRemedyResponse)
async def get_natural_remedy(request: NaturalRemedyRequest, current_user=Depends(get_current_user)):
    """
    Up to 2 simple homemade alternatives for a cosmetic (scanned barcode or label text). Costs 1 credit
    unless an answer for this product / ingredient list already exists. UNVERIFIED AI suggestion; the
    backend removes remedies with harsh ingredients and never suggests one for sunscreen, dyes,
    medicated, eye, lip or baby products.
    """
    try:
        return await ai_natural_remedy_service.get_remedy(str(current_user["_id"]), request)
    except ai.ProductNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    except ai_natural_remedy_service.NotCosmeticError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "not_cosmetic", "message": "Natural remedies are only available for cosmetics."})
    except ai.IngredientsMissingError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "ingredients_missing", "message": "No ingredient list for this product. Scan the ingredients label first."})
    except CreditsExhausted as e:
        raise _credits_exhausted(e)
    except ai.AIUnavailableError:
        raise _ai_unavailable()
