from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import check_ai_rate_limit
from app.schemas.ai_explain import AIExplainRequest, AIExplainResponse
from app.services.ai_explain_service import AIUnavailableError, explain_ingredients

router = APIRouter()


@router.post("/explain-ingredients", response_model=AIExplainResponse)
async def explain_unassessed_ingredients(
    request: AIExplainRequest,
    current_user=Depends(check_ai_rate_limit),
):
    """
    Opt-in: the user taps "Analyze with AI" on ingredients we could not assess.
    Returns an UNVERIFIED plain-English explanation per ingredient. It never changes the
    verdict or score and is stored only in its own cache, not in the safety database.
    """
    try:
        return await explain_ingredients(request.ingredients, request.category)
    except AIUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is not available right now. Please try again later.",
        )
