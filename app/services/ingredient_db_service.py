from typing import List, Dict, Any, Tuple, Optional
from app.db.mongodb import get_database
from app.services.ingredient_parser import ingredient_parser, ParseResult
from app.services.ingredient_matcher import ingredient_matcher, MatchResult
from app.services.rule_engine import rule_engine, EvaluationResult

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
        matched_results: List[Tuple[str, MatchResult, List[str]]] = []
        ingredient_ids_to_fetch = set()

        for parsed in parse_result.ingredients:
            # Match the main ingredient
            match_res: MatchResult = await ingredient_matcher.match(parsed.clean_name, db)
            matched_results.append((parsed.raw_text, match_res, parsed.sub_ingredients))

            if match_res.ingredient_id:
                ingredient_ids_to_fetch.add(match_res.ingredient_id)
            else:
                unknown_ingredients.append(parsed.clean_name)

            # Also check sub-ingredients if present (e.g. 'palm oil' inside 'vegetable oil')
            for sub_name in parsed.sub_ingredients:
                sub_match = await ingredient_matcher.match(sub_name, db)
                if sub_match.ingredient_id:
                    ingredient_ids_to_fetch.add(sub_match.ingredient_id)

        # 2. Batch fetch all facts for matched ingredients from MongoDB in 1 query
        facts_by_ing_id: Dict[str, List[Dict[str, Any]]] = {}
        if ingredient_ids_to_fetch:
            cursor = db.facts.find(
                {"ingredient_id": {"$in": list(ingredient_ids_to_fetch)}},
                {"_id": 0}
            )
            async for fact in cursor:
                i_id = str(fact.get("ingredient_id"))
                if i_id not in facts_by_ing_id:
                    facts_by_ing_id[i_id] = []
                facts_by_ing_id[i_id].append(fact)

        # 3. Assemble ingredients_data payload for rule engine
        for raw_name, match_res, sub_ingredients in matched_results:
            ing_facts: List[Dict[str, Any]] = []

            # Add facts for main ingredient
            if match_res.ingredient_id and match_res.ingredient_id in facts_by_ing_id:
                ing_facts.extend(facts_by_ing_id[match_res.ingredient_id])

            # Add facts from any sub-ingredients
            for sub_name in sub_ingredients:
                sub_match = await ingredient_matcher.match(sub_name, db)
                if sub_match.ingredient_id and sub_match.ingredient_id in facts_by_ing_id:
                    ing_facts.extend(facts_by_ing_id[sub_match.ingredient_id])

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
                "canonical_name": match_res.matched_alias,
                "matched": match_res.match_type in ("exact", "fuzzy", "suggested"),
                "match_type": match_res.match_type,
                "confidence": match_res.confidence,
                "facts": ing_facts
            })

        # 4. Pure evaluation via RuleEngine
        evaluation: EvaluationResult = rule_engine.evaluate(ingredients_data)

        return evaluation, unknown_ingredients

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

        if sev == "critical":
            verdict = "avoid"
            score = 15
            summary = "Contains an ingredient classified with critical hazard (e.g. WHO IARC Group 1 Carcinogen)."
        elif sev == "high":
            verdict = "avoid"
            score = 35
            summary = "Contains ingredient classified with high health/toxicological concern."
        elif sev == "medium":
            verdict = "caution"
            score = 60
            summary = "Contains ingredient with moderate concern or allergen advisory."
        elif sev == "low":
            verdict = "safe" if cov >= 0.7 else "caution"
            score = 80 if cov >= 0.7 else 70
            summary = "Low-concern ingredients identified."
        else:
            # sev == 'none'
            if cov >= 0.7:
                verdict = "safe"
                score = 90
                summary = "No classified toxicological hazards identified among recognised ingredients."
            else:
                verdict = "caution"
                score = 70
                summary = f"No hazards found in assessed ingredients, but coverage is {int(cov*100)}%."

        return verdict, score, summary

# Singleton instance
ingredient_db_service = IngredientDBService()
