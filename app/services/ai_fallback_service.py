import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.db.mongodb import get_database
from app.services.ai_service import ai_service
from scripts.common import normalize_name, upsert_source, upsert_ingredient, upsert_alias, upsert_fact

AI_SOURCE_METADATA = {
    "name": "ai_llm_proposal",
    "version": "1.0",
    "license_type": "Proprietary AI Inference",
    "attribution": "Automated AI Proposal (Unverified by Human)"
}

class AIFallbackService:
    """
    Handles sandboxed AI proposals for unrecognised ingredients:
    1. Caches unknown ingredients in MongoDB so the same chemical is never queried twice.
    2. Prompts Groq / Gemini to propose canonical name, category, and potential safety dimensions.
    3. Saves proposals into ai_review_queue with status='pending'.
    4. Records facts with verified=False and evidence_tier=4 (Lowest trust).
    """

    async def get_or_create_ai_source_id(self, db) -> str:
        """Ensures the AI fallback source entry exists in the sources collection."""
        return await upsert_source(
            db,
            name=AI_SOURCE_METADATA["name"],
            version=AI_SOURCE_METADATA["version"],
            license_type=AI_SOURCE_METADATA["license_type"],
            attribution=AI_SOURCE_METADATA["attribution"]
        )

    def _build_classification_prompt(self, ingredient_name: str, category: str) -> str:
        return f"""You are a scientific toxicologist and chemical classifier.
Analyze this unrecognised ingredient found on a consumer product label.

Ingredient Name: "{ingredient_name}"
Product Category: "{category}"

Respond with ONLY a raw JSON object (no markdown, no backticks, no code blocks):
{{
  "suggested_canonical_name": "standardized chemical or common name in lowercase",
  "category": "e.g. food_additive, surfactant, preservative, fragrance, herbal",
  "proposed_facts": [
    {{
      "dimension": "cancer_class | developmental | reproductive | regulatory | allergen | irritation",
      "value": "concise finding description",
      "severity": "low | medium | high | critical",
      "reason": "brief 1-sentence scientific reason"
    }}
  ]
}}

If the ingredient is a benign, safe common food item (e.g. starch, water, salt, wheat), return "proposed_facts": [].
Only flag real, established scientific or allergen concerns. Do not hallucinate."""

    async def process_unknown_ingredient(
        self,
        raw_ingredient_name: str,
        category: str = "food",
        db=None
    ) -> Optional[Dict[str, Any]]:
        """
        Processes a single unknown ingredient through the AI fallback pipeline.
        Safe and idempotent — reuses existing review queue entries if already seen.
        """
        if db is None:
            db = get_database()

        clean_name = normalize_name(raw_ingredient_name)
        if not clean_name:
            return None

        # 1. Check if this unknown ingredient is already in the review queue
        existing_review = await db.ai_review_queue.find_one({"raw_ingredient_name": clean_name})
        if existing_review:
            print(f"⚡ Ingredient '{clean_name}' already in review queue (status: {existing_review.get('status')}). Skipping AI call.")
            return existing_review

        # 2. Call AI (Groq -> Gemini fallback)
        print(f"🤖 Generating AI classification for unknown ingredient: '{clean_name}'")
        prompt = self._build_classification_prompt(clean_name, category)

        ai_response_text = None
        # Try Groq first, then Gemini
        try:
            if hasattr(ai_service, "_generate_with_groq_sync") and ai_service.groq_client:
                import asyncio
                loop = asyncio.get_event_loop()
                ai_response_text = await loop.run_in_executor(None, ai_service._generate_with_groq_sync, prompt)
        except Exception as e:
            print(f"⚠️ Groq failed for '{clean_name}' ({e}). Trying Gemini...")

        if not ai_response_text:
            try:
                if hasattr(ai_service, "_generate_with_gemini_sync") and ai_service.gemini_client:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    ai_response_text = await loop.run_in_executor(None, ai_service._generate_with_gemini_sync, prompt)
            except Exception as e:
                print(f"⚠️ Gemini failed for '{clean_name}': {e}")

        # 3. Parse JSON response safely
        proposed_data = None
        if ai_response_text:
            try:
                # Clean any markdown tags if present
                clean_json_str = re.sub(r"^```json\s*|\s*```$", "", ai_response_text.strip(), flags=re.MULTILINE)
                proposed_data = json.loads(clean_json_str)
            except Exception as parse_err:
                print(f"⚠️ Could not parse AI response JSON for '{clean_name}': {parse_err}")

        if not proposed_data:
            # Fallback safe skeleton
            proposed_data = {
                "suggested_canonical_name": clean_name,
                "category": category,
                "proposed_facts": []
            }

        suggested_canonical = normalize_name(proposed_data.get("suggested_canonical_name") or clean_name)
        proposed_facts = proposed_data.get("proposed_facts", [])

        # 4. Insert into ai_review_queue
        queue_doc = {
            "raw_ingredient_name": clean_name,
            "suggested_canonical_name": suggested_canonical,
            "category": proposed_data.get("category", category),
            "proposed_facts": proposed_facts,
            "status": "pending",
            "reviewed_at": None,
            "notes": None,
            "created_at": datetime.utcnow()
        }
        review_result = await db.ai_review_queue.insert_one(queue_doc)
        queue_id = str(review_result.inserted_id)

        # 5. Save into database as unverified Tier 4 data
        ai_source_id = await self.get_or_create_ai_source_id(db)

        # Create ingredient entity
        ing_id = await upsert_ingredient(
            db,
            canonical_name=suggested_canonical,
            category=proposed_data.get("category", category),
            description="AI-generated proposal (Awaiting human verification)"
        )

        # Map the raw scanned label name to this ingredient as an alias
        await upsert_alias(db, clean_name, ing_id, alias_type="ai_proposal")

        # Save facts with verified=False and evidence_tier=4
        for f in proposed_facts:
            dim = f.get("dimension")
            val = f.get("value")
            sev = f.get("severity", "medium")
            if dim and val:
                await upsert_fact(
                    db,
                    ingredient_id=ing_id,
                    source_id=ai_source_id,
                    dimension=dim,
                    value=val,
                    severity=sev,
                    evidence_tier=4,       # Tier 4: AI Unverified
                    verified=False,        # Explicitly unverified!
                    conditions=f.get("reason")
                )

        print(f"✅ Queued '{clean_name}' in ai_review_queue (ID: {queue_id}) as Tier 4 unverified.")
        return queue_doc

# Singleton fallback instance
ai_fallback_service = AIFallbackService()
