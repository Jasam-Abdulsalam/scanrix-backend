"""AI alternatives for a scanned product (POST /ai/alternatives).

Same money rules as 'Get AI verdict' (ai_product_service): an answer that already exists for this
product is free; a new one costs 1 weekly credit, refunded when the AI gives nothing usable.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.crud import crud_ai_alternatives
from app.crud.crud_product import get_product_by_barcode
from app.schemas.ai_alternatives import AIAlternativesResponse, AIAlternativesResult
from app.services import credits_service, product_image_service
from app.services.ai_alternatives_rules import build_prompt, clean_result, flagged_ingredients, parse_alternatives
from app.services.ai_analysis_rules import make_cache_key
from app.services.ai_product_service import (
    AIUnavailableError, IngredientsMissingError, ProductNotFoundError, _generate, _product_text,
)
from app.services.ingredient_db_service import ingredient_db_service
from app.services.ingredient_parser import ingredient_parser

logger = logging.getLogger(__name__)
ACTION = "ai_alternatives"

__all__ = ["get_alternatives", "AIUnavailableError", "IngredientsMissingError", "ProductNotFoundError"]


def _response(result: dict, cached: bool, remaining: Optional[int], at: Optional[datetime]) -> AIAlternativesResponse:
    return AIAlternativesResponse(**result, cached=cached, credits_remaining=remaining, generated_at=at)


async def get_alternatives(user_id: str, barcode: str) -> AIAlternativesResponse:
    product = await get_product_by_barcode(barcode)
    if not product:
        raise ProductNotFoundError(barcode)
    text = _product_text(product)
    names = [i.clean_name for i in ingredient_parser.parse(text).ingredients]
    if not names:
        raise IngredientsMissingError()
    # Same barcode + same ingredient list = same answer; a reformulated product gets a new one.
    key = make_cache_key(barcode, product.get("category", "food"), names)

    hit = await crud_ai_alternatives.get_cached(key)
    if hit:  # free: nobody pays twice for an answer that already exists
        balance = await credits_service.get_balance(user_id)
        return _response(hit["result"], True, balance.remaining, hit.get("created_at"))

    reservation = await credits_service.reserve_credit(user_id, ACTION)  # raises CreditsExhausted
    try:
        result, model = await _run_ai(product, text, names)
    except Exception:
        await credits_service.refund_credit(reservation)  # includes AIUnavailableError: nothing usable, nothing saved
        raise
    try:
        await crud_ai_alternatives.save_alternatives(key, result.model_dump(), barcode, model)
    except Exception as e:  # noqa: BLE001 - the user still gets the answer they paid for; only the cache is lost
        logger.warning("Could not cache AI alternatives: %s", type(e).__name__)
    balance = await credits_service.get_balance(user_id)
    return _response(result.model_dump(), False, balance.remaining, datetime.now(timezone.utc))


async def _run_ai(product: dict, text: str, names: list) -> tuple[AIAlternativesResult, str]:
    """(cleaned result, model name). Raises AIUnavailableError when the AI gave nothing usable."""
    evaluation, _ = await ingredient_db_service.analyze_ingredients_text(text, category=product.get("category", "food"))
    flagged = flagged_ingredients(evaluation)
    raw, model = await _generate(build_prompt(product, names, flagged))
    parsed = parse_alternatives(raw)
    if parsed is None:
        # length + tail tell truncation apart from a wrong shape; never log the full text
        logger.warning("AI alternatives from %s rejected: %d chars, ends with %r", model, len(raw or ""), (raw or "")[-40:])
        raise AIUnavailableError("no usable AI answer")
    # An empty list is a valid answer ("no confident alternative"): saved and shown as such, not retried.
    cleaned = clean_result(parsed, names, flagged)
    return await _with_images(cleaned, product.get("category") == "cosmetic"), model


async def _with_images(result: AIAlternativesResult, cosmetic: bool) -> AIAlternativesResult:
    """Adds a photo to each alternative, looked up in parallel. Best effort and time-boxed: if the
    lookups take longer than PRODUCT_IMAGES_TOTAL_SECONDS, the answer is returned without photos."""
    if not result.alternatives:
        return result
    lookups = [product_image_service.find_image(a.name, a.brand, a.size, cosmetic) for a in result.alternatives]
    try:
        urls = await asyncio.wait_for(asyncio.gather(*lookups), settings.PRODUCT_IMAGES_TOTAL_SECONDS)
    except asyncio.TimeoutError:
        logger.info("Product image lookups timed out; answering without photos")
        return result
    alts = [a.model_copy(update={"image_url": url}) for a, url in zip(result.alternatives, urls)]
    return result.model_copy(update={"alternatives": alts})
