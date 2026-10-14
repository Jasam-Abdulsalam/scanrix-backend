import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.crud import crud_ai_analysis
from app.crud.crud_product import get_product_by_barcode
from app.schemas.ai_analysis import AIAnalyzeRequest, AIAnalyzeResponse
from app.services import credits_service
from app.services.ai_analysis_rules import apply_guardrails, build_prompt, make_cache_key, parse_analysis
from app.services.ai_service import ai_service
from app.services.ingredient_db_service import ingredient_db_service
from app.services.ingredient_parser import ingredient_parser

logger = logging.getLogger(__name__)
ACTION = "ai_verdict"


class AIUnavailableError(Exception):
    """No usable AI answer (provider down, timeout, unusable output). Nothing was saved; credit refunded."""


class IngredientsMissingError(Exception):
    """No ingredient list to analyse: the user should scan the ingredients label."""


class ProductNotFoundError(Exception):
    pass


async def _generate(prompt: str) -> Tuple[Optional[str], str]:
    """Groq first, then Gemini. Sync SDK calls run in a thread, each bounded by a timeout."""
    providers = [("groq", ai_service._generate_with_groq_sync), ("gemini", ai_service._generate_with_gemini_sync)]
    for model, call in providers:
        try:
            text = await asyncio.wait_for(asyncio.to_thread(call, prompt), settings.AI_ANALYSIS_TIMEOUT_SECONDS)
            if text:
                return text, model
        except Exception as e:  # noqa: BLE001 - any provider failure just moves on to the next one
            logger.warning("AI provider %s failed: %s", model, type(e).__name__)
    return None, ""


def _product_text(product: Dict[str, Any]) -> str:
    names = [i.get("name", "") for i in product.get("ingredients", []) if isinstance(i, dict)]
    return ", ".join(n for n in names if n)


async def resolve_source(request: AIAnalyzeRequest) -> Tuple[Optional[dict], str, str]:
    """(product or None, ingredient text, category). Raises ProductNotFoundError / IngredientsMissingError."""
    if request.barcode:
        product = await get_product_by_barcode(request.barcode)
        if not product:
            raise ProductNotFoundError(request.barcode)
        return product, _product_text(product), product.get("category", "food")
    return None, request.ingredients_text or "", request.category


def _names_and_key(text: str, barcode: Optional[str], category: str) -> Tuple[List[str], str]:
    names = [i.clean_name for i in ingredient_parser.parse(text).ingredients]
    if not names:
        raise IngredientsMissingError()
    return names, make_cache_key(barcode, category, names)


def _response(stored: Dict[str, Any], cached: bool, remaining: Optional[int], at: Optional[datetime]) -> AIAnalyzeResponse:
    return AIAnalyzeResponse(**stored, cached=cached, credits_remaining=remaining, generated_at=at)


async def analyze_product(user_id: str, request: AIAnalyzeRequest) -> AIAnalyzeResponse:
    product, text, category = await resolve_source(request)
    names, key = _names_and_key(text, request.barcode, category)

    hit = await crud_ai_analysis.get_cached(key)
    if hit:  # free: nobody pays twice for an answer that already exists
        balance = await credits_service.get_balance(user_id)
        return _response(hit["analysis"], True, balance.remaining, hit.get("created_at"))

    reservation = await credits_service.reserve_credit(user_id, ACTION)  # raises CreditsExhausted
    try:
        result = await _run_ai(product, category, text, names)
    except Exception:
        await credits_service.refund_credit(reservation)  # includes AIUnavailableError: nothing usable, nothing saved
        raise
    try:
        await crud_ai_analysis.save_analysis(key, result[0].model_dump(), category, result[1], request.barcode)
    except Exception as e:  # noqa: BLE001 - the user still gets the answer they paid for; only the cache is lost
        logger.warning("Could not cache AI analysis: %s", type(e).__name__)
    balance = await credits_service.get_balance(user_id)
    return _response(result[0].model_dump(), False, balance.remaining, datetime.now(timezone.utc))


async def _run_ai(product: Optional[dict], category: str, text: str, names: List[str]):
    """(guardrailed analysis, model name). Raises AIUnavailableError when the AI gave nothing usable."""
    evaluation, unknown = await ingredient_db_service.analyze_ingredients_text(text, category=category)
    prompt = build_prompt((product or {}).get("name"), category, names, evaluation, unknown)
    raw, model = await _generate(prompt)
    parsed = parse_analysis(raw)
    if parsed is None:
        raise AIUnavailableError("no usable AI answer")
    return apply_guardrails(parsed, evaluation), model


async def cached_analysis_for_product(product: Dict[str, Any]) -> Optional[AIAnalyzeResponse]:
    """Lookup only (never calls the AI, never costs a credit): used when a product is reopened."""
    text = _product_text(product)
    if not text:
        return None
    try:
        _, key = _names_and_key(text, product.get("barcode"), product.get("category", "food"))
    except IngredientsMissingError:
        return None
    hit = await crud_ai_analysis.get_cached(key)
    return _response(hit["analysis"], True, None, hit.get("created_at")) if hit else None
