"""Homemade natural remedy for a scanned cosmetic (POST /ai/natural-remedy).

Same money rules as 'Get AI verdict' (ai_product_service): an answer that already exists for this product
(or this label's ingredient list) is free; a new one costs 1 weekly credit, refunded when the AI gives
nothing usable. The safety rules are enforced in ai_natural_remedy_rules.clean_result.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.crud import crud_ai_natural_remedy
from app.schemas.ai_natural_remedy import AINaturalRemedyResponse, AINaturalRemedyResult, NaturalRemedyRequest
from app.services import credits_service
from app.services.ai_natural_remedy_rules import build_prompt, clean_result, parse_result
from app.services.ai_product_service import (
    AIUnavailableError, IngredientsMissingError, ProductNotFoundError, _generate, _names_and_key, resolve_source,
)

logger = logging.getLogger(__name__)
ACTION = "ai_natural_remedy"

__all__ = ["get_remedy", "AIUnavailableError", "IngredientsMissingError", "NotCosmeticError", "ProductNotFoundError"]


class NotCosmeticError(Exception):
    """Natural remedies are only for cosmetics (not food or household products)."""


def _response(result: dict, cached: bool, remaining: Optional[int], at: Optional[datetime]) -> AINaturalRemedyResponse:
    return AINaturalRemedyResponse(**result, cached=cached, credits_remaining=remaining, generated_at=at)


async def get_remedy(user_id: str, request: NaturalRemedyRequest) -> AINaturalRemedyResponse:
    product, text, category = await resolve_source(request)  # raises ProductNotFoundError
    if category != "cosmetic":
        raise NotCosmeticError()
    names, key = _names_and_key(text, request.barcode, category)  # raises IngredientsMissingError

    hit = await crud_ai_natural_remedy.get_cached(key)
    if hit:  # free: nobody pays twice for an answer that already exists
        balance = await credits_service.get_balance(user_id)
        return _response(hit["result"], True, balance.remaining, hit.get("created_at"))

    reservation = await credits_service.reserve_credit(user_id, ACTION)  # raises CreditsExhausted
    try:
        result, model = await _run_ai(product, names)
    except Exception:
        await credits_service.refund_credit(reservation)  # includes AIUnavailableError: nothing usable, nothing saved
        raise
    try:
        await crud_ai_natural_remedy.save_remedy(key, result.model_dump(), request.barcode, model)
    except Exception as e:  # noqa: BLE001 - the user still gets the answer they paid for; only the cache is lost
        logger.warning("Could not cache AI natural remedy: %s", type(e).__name__)
    balance = await credits_service.get_balance(user_id)
    return _response(result.model_dump(), False, balance.remaining, datetime.now(timezone.utc))


async def _run_ai(product: Optional[dict], names: List[str]) -> tuple[AINaturalRemedyResult, str]:
    """(safety-cleaned result, model name). Raises AIUnavailableError when the AI gave nothing usable."""
    raw, model = await _generate(build_prompt(product, names))
    parsed = parse_result(raw)
    if parsed is None:
        # length + tail tell truncation apart from a wrong shape; never log the full text
        logger.warning("AI natural remedy from %s rejected: %d chars, ends with %r", model, len(raw or ""), (raw or "")[-40:])
        raise AIUnavailableError("no usable AI answer")
    # No remedy (unsafe product type, or nothing passed the checks) is a valid, saved answer, not an error.
    return clean_result(parsed, (product or {}).get("name")), model
