import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.ai_analysis import AIAnalyzeRequest, AIAnalyzeResponse, CreditsResponse
from app.services import ai_product_service as ai
from app.services import credits_service
from app.services.credits_service import CreditsExhausted

router = APIRouter()


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
        wait = max(math.ceil((e.resets_at - datetime.now(timezone.utc)).total_seconds()), 1)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait)}, detail={
            "code": "ai_credits_exhausted", "message": "You have used all AI credits for this week.",
            "resets_at": e.resets_at.isoformat()})
    except ai.AIUnavailableError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "ai_unavailable", "message": "AI analysis is not available right now. You were not charged. Please try again later."})
