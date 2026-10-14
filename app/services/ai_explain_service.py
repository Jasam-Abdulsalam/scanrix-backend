import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.core.config import settings
from app.crud.crud_ai_explanation import find_cached, save_explanations
from app.schemas.ai_explain import AIExplainResponse, AIExplanationItem
from app.services.ai_service import ai_service
from app.services.ingredient_db_service import ingredient_db_service
from app.services.ingredient_matcher import ingredient_matcher
from app.services.ingredient_parser import ingredient_parser

logger = logging.getLogger(__name__)


class AIUnavailableError(Exception):
    """No usable AI answer (provider down, timeout, or unusable output). Nothing was saved."""


def build_prompt(names: List[str], category: str) -> str:
    # Names travel as a JSON list (data), after validation: they can't add instructions.
    return (
        "You explain ingredients found on consumer product labels, in plain English for shoppers.\n"
        f"Product category: {category}\n"
        f"Ingredient names (JSON list): {json.dumps(names)}\n\n"
        "For EACH name return what it is, what it is used for, and effects that are commonly reported "
        "(for example skin irritation or allergy). Do NOT judge whether a product is safe. "
        "If you are not sure what an ingredient is, set certainty to \"unknown\" and say so; never guess.\n"
        "Respond with ONLY raw JSON, no markdown:\n"
        '{"ingredients": [{"name": "<exactly as given>", "summary": "1-2 sentences", '
        '"used_for": ["..."], "possible_effects": ["..."], "certainty": "well_known | uncertain | unknown"}]}'
    )


def parse_ai_output(text: Optional[str], requested: List[str]) -> List[AIExplanationItem]:
    """Valid items only. Wrong names, bad shapes and over-long text are dropped, never repaired."""
    if not text:
        return []
    try:
        data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE))
        raw_items = data["ingredients"]
    except (ValueError, KeyError, TypeError):
        return []
    wanted, items = set(requested), {}
    for raw in (raw_items if isinstance(raw_items, list) else []):
        try:
            item = AIExplanationItem(**raw)
        except (ValidationError, TypeError):
            continue
        name = ingredient_parser.normalize_ingredient_token(item.name)
        if name in wanted and name not in items:
            items[name] = item.model_copy(update={"name": name})
    return list(items.values())


async def _generate(prompt: str) -> Tuple[Optional[str], str]:
    """Groq first, then Gemini. Sync SDK calls run in a thread, each bounded by a timeout."""
    providers = [("groq", ai_service._generate_with_groq_sync), ("gemini", ai_service._generate_with_gemini_sync)]
    for model, call in providers:
        try:
            text = await asyncio.wait_for(asyncio.to_thread(call, prompt), settings.AI_EXPLAIN_TIMEOUT_SECONDS)
            if text:
                return text, model
        except Exception as e:  # noqa: BLE001 - any provider failure just moves on to the next one
            logger.warning("AI provider %s failed: %s", model, type(e).__name__)
    return None, ""


async def _split_known(names: List[str]) -> Tuple[List[str], List[str]]:
    """(names our database does not recognise, names it does). Only unknown names may be explained,
    so the endpoint cannot be used as a general-purpose chatbot."""
    await ingredient_db_service.ensure_matcher_ready()
    unknown, known = [], []
    for name in names:
        match = await ingredient_matcher.match(name, None)
        (known if match.ingredient_id else unknown).append(name)
    return unknown, known


async def explain_ingredients(raw_names: List[str], category: str) -> AIExplainResponse:
    names = list(dict.fromkeys(n for n in (ingredient_parser.normalize_ingredient_token(r) for r in raw_names) if n))
    unknown, known = await _split_known(names)
    cached: Dict[str, Any] = await find_cached(unknown, category)
    missing = [n for n in unknown if n not in cached]
    fresh: List[AIExplanationItem] = []
    if missing:
        text, model = await _generate(build_prompt(missing, category))
        fresh = parse_ai_output(text, missing)
        if not fresh:
            raise AIUnavailableError("no usable AI answer")  # nothing saved: the user can retry
        await save_explanations([f.model_dump() for f in fresh], category, model)
    by_name = {**{n: AIExplanationItem(**c) for n, c in cached.items()}, **{f.name: f for f in fresh}}
    return AIExplainResponse(
        explanations=[by_name[n] for n in unknown if n in by_name],
        already_assessed=known,
        unavailable=[n for n in unknown if n not in by_name],
    )
