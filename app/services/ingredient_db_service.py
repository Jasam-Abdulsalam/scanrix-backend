from typing import List, Dict, Any, Tuple, Optional
import logging

from app.crud.crud_unknown_ingredient import record_unknown_ingredients
from app.db.mongodb import get_database
from app.services.ingredient_parser import ingredient_parser, ParseResult
from app.services.ingredient_matcher import ingredient_matcher, MatchResult
from app.services.rule_engine import rule_engine, EvaluationResult

logger = logging.getLogger(__name__)

# Minimum share of recognised ingredients before a no-hazard result may be called "safe" (judgment).
SAFE_MIN_COVERAGE = 0.7

class IngredientDBService:
    """
    Orchestration service that bridges raw packaging text to the rule engine:
    1. Parses raw text via IngredientParser
    2. Matches ingredients via IngredientMatcher (using in-memory cache)
    3. Fetches verified facts from MongoDB
    4. Evaluates risk via RuleEngine
    5. Formats backwards-compatible score & verdict for existing mobile screens
    """

    async def ensure_matcher_ready(self, db=None):
        """Ensures the in-memory alias cache is loaded for instant lookups."""
        if not ingredient_matcher._is_loaded:
            if db is None:
                db = get_database()
            await ingredient_matcher.load_cache(db)

    async def _exact_sub_ingredient_ids(self, sub_names: List[str], db) -> List[str]:
        """Ids of sub-ingredients that match an alias EXACTLY. Fuzzy/suggested sub-matches
        are ignored: a bracketed word like '(natural)' must not pass facts to its parent."""
        ids: List[str] = []
        for name in sub_names:
            res = await ingredient_matcher.match(name, db)
            if res.match_type == "exact" and res.ingredient_id:
                ids.append(res.ingredient_id)
        return ids

    async def analyze_ingredients_text(
        self,
        raw_text: str,
        category: str = "food",
        db=None
    ) -> Tuple[EvaluationResult, List[str]]:
        """
        Main entry point for analyzing ingredient text.
        Returns:
            (EvaluationResult, list_of_unknown_ingredients_for_ai_fallback)
        """
        if db is None:
            db = get_database()

        await self.ensure_matcher_ready(db)

        # 1. Parse text into structured tokens
        parse_result: ParseResult = ingredient_parser.parse(raw_text)

        ingredients_data: List[Dict[str, Any]] = []
        unknown_ingredients: List[str] = []

        # Collect all matched ingredient IDs for a single batched MongoDB query
        matched_results: List[Tuple[str, MatchResult, List[str]]] = []  # (raw, match, exact sub-ingredient ids)
        ingredient_ids_to_fetch = set()

        for parsed in parse_result.ingredients:
            # Match the main ingredient
            match_res: MatchResult = await ingredient_matcher.match(parsed.clean_name, db)
            sub_ids = await self._exact_sub_ingredient_ids(parsed.sub_ingredients, db)
            matched_results.append((parsed.raw_text, match_res, sub_ids))
            ingredient_ids_to_fetch.update(sub_ids)

            if match_res.ingredient_id:
                ingredient_ids_to_fetch.add(match_res.ingredient_id)
            else:
                unknown_ingredients.append(parsed.clean_name)


        # 2. Batch fetch all facts for matched ingredients from MongoDB in 1 query
        facts_by_ing_id: Dict[str, List[Dict[str, Any]]] = {}
        if ingredient_ids_to_fetch:
            cursor = db.facts.find(
                {"ingredient_id": {"$in": list(ingredient_ids_to_fetch)}},
                {"_id": 0}
            )
            async for fact in cursor:
                if fact.get("applies_to") not in (None, category):
                    continue  # e.g. EU cosmetics rules must not flag a food product
                i_id = str(fact.get("ingredient_id"))
                if i_id not in facts_by_ing_id:
                    facts_by_ing_id[i_id] = []
                facts_by_ing_id[i_id].append(fact)

        # 3. Assemble ingredients_data payload for rule engine
        for raw_name, match_res, sub_ids in matched_results:
            ing_facts: List[Dict[str, Any]] = []

            # Add facts for main ingredient
            if match_res.ingredient_id and match_res.ingredient_id in facts_by_ing_id:
                ing_facts.extend(facts_by_ing_id[match_res.ingredient_id])

            # Add facts from sub-ingredients that matched EXACTLY
            for sub_id in sub_ids:
                ing_facts.extend(facts_by_ing_id.get(sub_id, []))

            # Also inject precautionary allergen facts if declared on package
            for allergen in parse_result.allergens_declared:
                if allergen in raw_name.lower():
                    ing_facts.append({
                        "dimension": "allergen",
                        "value": f"precautionary_allergen_{allergen}",
                        "severity": "medium",
                        "evidence_tier": 2
                    })

            ingredients_data.append({
                "raw_name": raw_name,
                "canonical_name": match_res.matched_alias if match_res.ingredient_id else None,
                "matched": match_res.ingredient_id is not None,
                "match_type": match_res.match_type,
                "confidence": match_res.confidence,
                "facts": ing_facts
            })

        # 4. Pure evaluation via RuleEngine
        evaluation: EvaluationResult = rule_engine.evaluate(ingredients_data)
        evaluation.declared_allergens = parse_result.contains_declared
        evaluation.may_contain_allergens = parse_result.allergens_declared

        return evaluation, unknown_ingredients

    async def evaluate_stored_product(
        self,
        ingredients: List[Any],
        category: str = "food"
    ) -> Tuple[Optional[EvaluationResult], List[str]]:
        """
        Re-evaluates a stored product's ingredient list (list of {"name": ...} dicts).
        Returns (None, []) when there is no ingredient text to assess.
        """
        names = [i.get("name", "") for i in ingredients if isinstance(i, dict)]
        text = ", ".join(n for n in names if n)
        if not text:
            return None, []
        return await self.analyze_ingredients_text(text, category=category)

    async def evaluate_product_ingredients(
        self,
        ingredients: List[Any],
        category: str = "food"
    ) -> Optional[EvaluationResult]:
        """Evaluation only (used where no scan is happening, so nothing is counted)."""
        evaluation, _ = await self.evaluate_stored_product(ingredients, category)
        return evaluation

    async def record_unknowns(self, names: List[str], category: str, barcode: Optional[str] = None) -> None:
        """Best-effort scan counter for unrecognised names: a failure must never break a scan."""
        try:
            await record_unknown_ingredients(names, category, barcode)
        except Exception as e:  # noqa: BLE001 - deliberate: counter is non-essential, logged below
            logger.warning("Could not record unknown ingredients: %s", type(e).__name__)

    def overlay_legacy_fields(self, product: Dict[str, Any], evaluation: Optional[EvaluationResult]) -> Dict[str, Any]:
        """
        Returns a copy of the product dict whose verdict/overall_score/summary come from a
        fresh evaluation, so they can never disagree with `safety_engine`. The stored values
        were computed at first-scan time and go stale when the ruleset or data changes.
        With no evaluation (no ingredient text) the stored values are kept.
        """
        if evaluation is None:
            return product
        verdict, score, summary = self.calculate_legacy_verdict_and_score(evaluation)
        return {**product, "verdict": verdict, "overall_score": score, "summary": summary}

    def calculate_legacy_verdict_and_score(
        self,
        evaluation: EvaluationResult
    ) -> Tuple[str, int, str]:
        """
        Maps the multi-dimension evaluation into backward-compatible
        (verdict, overall_score, summary) fields expected by older mobile clients.
        """
        sev = evaluation.overall_severity
        cov = evaluation.coverage
        recognised, total = evaluation.recognised_count, evaluation.total_count

        # A flagged hazard always wins, whatever the coverage.
        if sev == "critical":
            return "avoid", 15, "Contains an ingredient classified with critical hazard (e.g. WHO IARC Group 1 Carcinogen)."
        if sev == "high":
            return "avoid", 35, "Contains ingredient classified with high health/toxicological concern."
        if sev == "medium":
            return "caution", 60, "Contains ingredient with moderate concern or allergen advisory."

        # No hazard flagged: never imply "safe" for ingredients we could not assess.
        if total == 0:
            return "unknown", 50, "No ingredients could be read from the text."
        if recognised == 0:
            return "unknown", 50, f"Not enough data: none of the {total} ingredients are in our database yet."
        if cov < SAFE_MIN_COVERAGE:
            # Score stays below 70 so the app never paints it as a "good" (green) result.
            return "caution", 55, (
                f"No classified hazards found in the {recognised} of {total} ingredients we could assess; "
                "the rest are not assessed."
            )
        if sev == "low":
            return "safe", 80, "Low-concern ingredients identified."
        return "safe", 90, "No classified toxicological hazards identified among recognised ingredients."


# Singleton instance
ingredient_db_service = IngredientDBService()
