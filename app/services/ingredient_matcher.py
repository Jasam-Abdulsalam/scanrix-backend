from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from rapidfuzz import process, fuzz
from app.db.mongodb import get_database

class MatchResult(BaseModel):
    query_text: str = Field(..., description="The input text that was searched")
    ingredient_id: Optional[str] = Field(None, description="MongoDB ingredient _id if matched")
    matched_alias: Optional[str] = Field(None, description="The alias string that matched")
    match_type: str = Field(..., description="'exact' | 'fuzzy' | 'suggested' | 'unknown'")
    confidence: float = Field(..., description="Match confidence score between 0.0 and 1.0")

class IngredientMatcher:
    """
    Matches parsed ingredient names against the database knowledge base.
    Features:
    1. In-memory alias cache for sub-millisecond lookups.
    2. Exact matching (confidence = 1.0).
    3. Fuzzy matching via RapidFuzz (handles OCR typos and minor misspellings).
    4. Three confidence tiers:
       - Exact or score >= 90: Accepted match
       - Score 70-89: Low-confidence suggestion (flagged for caution)
       - Score < 70: Unknown (sent to AI fallback)
    """

    def __init__(self):
        # In-memory dictionary: { normalized_alias: ingredient_id }
        self._alias_map: Dict[str, str] = {}
        # List of all alias strings for rapidfuzz matching
        self._all_aliases: List[str] = []
        self._is_loaded = False

    async def load_cache(self, db=None):
        """
        Loads all aliases into memory.
        Call this at app startup or when seeding completes.
        Takes only ~2-5 MB of RAM for tens of thousands of aliases!
        """
        if db is None:
            db = get_database()

        print("📦 Loading aliases into memory cache...")
        cursor = db.aliases.find({}, {"normalized_alias": 1, "ingredient_id": 1})
        new_map = {}
        async for doc in cursor:
            alias = doc.get("normalized_alias")
            ing_id = str(doc.get("ingredient_id"))
            if alias and ing_id:
                new_map[alias] = ing_id

        self._alias_map = new_map
        self._all_aliases = list(new_map.keys())
        self._is_loaded = True
        print(f"✅ Loaded {len(self._all_aliases)} aliases into memory cache!")

    async def match(self, text: str, db=None) -> MatchResult:
        """
        Matches an ingredient name against the database/cache.
        """
        if not text:
            return MatchResult(
                query_text="",
                ingredient_id=None,
                matched_alias=None,
                match_type="unknown",
                confidence=0.0
            )

        norm_query = text.strip().lower()

        # 1. Check in-memory cache if loaded
        if self._is_loaded:
            # Step A: Exact match in cache
            if norm_query in self._alias_map:
                return MatchResult(
                    query_text=text,
                    ingredient_id=self._alias_map[norm_query],
                    matched_alias=norm_query,
                    match_type="exact",
                    confidence=1.0
                )

            # Step B: Fuzzy match in cache if we have aliases
            if self._all_aliases:
                best_match = process.extractOne(
                    norm_query,
                    self._all_aliases,
                    scorer=fuzz.WRatio,
                    score_cutoff=70.0
                )

                if best_match:
                    matched_alias, score, _ = best_match
                    confidence = round(score / 100.0, 2)
                    matched_id = self._alias_map[matched_alias]

                    if score >= 90.0:
                        return MatchResult(
                            query_text=text,
                            ingredient_id=matched_id,
                            matched_alias=matched_alias,
                            match_type="fuzzy",
                            confidence=confidence
                        )
                    else:
                        # 70 <= score < 90: Low confidence suggestion
                        return MatchResult(
                            query_text=text,
                            ingredient_id=matched_id,
                            matched_alias=matched_alias,
                            match_type="suggested",
                            confidence=confidence
                        )

            # No cache match above 70 score -> Unknown
            return MatchResult(
                query_text=text,
                ingredient_id=None,
                matched_alias=None,
                match_type="unknown",
                confidence=0.0
            )

        # 2. Fallback to direct DB query if cache was not initialized
        if db is None:
            db = get_database()

        # Direct DB exact match
        exact_doc = await db.aliases.find_one({"normalized_alias": norm_query})
        if exact_doc:
            return MatchResult(
                query_text=text,
                ingredient_id=str(exact_doc["ingredient_id"]),
                matched_alias=norm_query,
                match_type="exact",
                confidence=1.0
            )

        # If cache isn't loaded and no exact match in DB, mark as unknown
        return MatchResult(
            query_text=text,
            ingredient_id=None,
            matched_alias=None,
            match_type="unknown",
            confidence=0.0
        )

# Singleton matcher instance
ingredient_matcher = IngredientMatcher()
