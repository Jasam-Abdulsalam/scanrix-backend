"""
Seeds Open Food Facts taxonomies (additives, ingredients, allergens) as RECOGNITION data.

This source says what an ingredient is, what it is used for and which allergen it
belongs to. It contains NO hazard classification, so it never raises a warning:
- 'function' facts are informational (severity 'none')
- 'allergen' facts use value 'allergen_info:<names>' (severity 'low', informational)

Licence: ODbL 1.0 (database) / DbCL 1.0 (contents), https://world.openfoodfacts.org/data
Attribution required: "Contains data from Open Food Facts, available under the Open Database License".
English names only (decision 2026-10-13: other languages risk false matches).

Run: python -m scripts.seed_off   (re-runs are safe: upserts, no duplicates)
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from scripts.common import normalize_name, upsert_source, upsert_ingredient, upsert_alias, upsert_fact

OFF_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "off"

SOURCE_METADATA = {
    "name": "openfoodfacts_taxonomies",
    "version": "2026-10-13",  # download date of the taxonomy snapshot
    "license_type": "ODbL 1.0 (database) / DbCL 1.0 (contents)",
    "url": "https://world.openfoodfacts.org/data",
    "attribution": "Contains data from Open Food Facts, available under the Open Database License",
}
# Community-curated reference data: informational, not an official regulatory source.
INFO_TIER = 3
INFO_VERIFIED = False


def load_taxonomy(name: str) -> Dict[str, dict]:
    with open(OFF_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def english_name(entry: dict) -> Optional[str]:
    """English name without the 'E450vi - ' prefix additives carry. None if missing."""
    raw = entry.get("name", {}).get("en")
    if not raw:
        return None
    name = normalize_name(re.sub(r"^e\d+[a-z]*\s*-\s*", "", raw, flags=re.IGNORECASE))
    return name or None


def parse_functions(entry: dict) -> List[str]:
    """'en:emulsifier, en:humectant' -> ['emulsifier', 'humectant']."""
    raw = entry.get("additives_classes", {}).get("en", "")
    return [c.strip().removeprefix("en:").replace("-", " ") for c in raw.split(",") if c.strip().startswith("en:")]


def allergen_name(allergen_id: str) -> str:
    return allergen_id.removeprefix("en:").replace("-", " ")


def resolve_allergens(ingredients: Dict[str, dict], valid: Set[str]) -> Dict[str, List[str]]:
    """Own allergens plus those inherited through the parent chain (casein -> milk proteins -> milk).
    Resolved once here so scans stay a plain lookup. O(ingredients * depth) with memoisation."""
    memo: Dict[str, Set[str]] = {}

    def resolve(key: str, path: tuple = ()) -> Set[str]:
        if key in memo:
            return memo[key]
        entry = ingredients.get(key)
        if entry is None or key in path:  # unknown parent or a cycle
            return set()
        own = {a.strip() for a in entry.get("allergens", {}).get("en", "").split(",")} & valid
        inherited = set().union(*(resolve(p, path + (key,)) for p in entry.get("parents", [])), set())
        memo[key] = own | inherited
        return memo[key]

    return {k: sorted(allergen_name(a) for a in resolve(k)) for k in ingredients if resolve(k)}


async def add_function_fact(db, ing_id: str, source_id: str, functions: List[str]):
    if functions:
        await upsert_fact(db, ing_id, source_id, "function", ", ".join(functions),
                          severity="none", evidence_tier=INFO_TIER, verified=INFO_VERIFIED)


async def add_allergen_fact(db, ing_id: str, source_id: str, allergens: List[str]):
    if allergens:
        await upsert_fact(db, ing_id, source_id, "allergen", "allergen_info:" + ",".join(allergens),
                          severity="low", evidence_tier=INFO_TIER, verified=INFO_VERIFIED,
                          conditions="Informational: relevant only to people with this allergy")


async def seed_additives(db, source_id: str) -> int:
    count = 0
    for key, entry in load_taxonomy("additives").items():
        code = normalize_name(key.removeprefix("en:"))
        if not code:
            continue
        ing_id = await upsert_ingredient(db, code, category="food_additive",
                                         description="Food additive (Open Food Facts taxonomy)")
        name = english_name(entry)
        if name and name != code:
            await upsert_alias(db, name, ing_id, alias_type="common_name")
        await add_function_fact(db, ing_id, source_id, parse_functions(entry))
        count += 1
    return count


async def seed_ingredients(db, source_id: str) -> Dict[str, int]:
    ingredients = load_taxonomy("ingredients")
    valid = {a for a in load_taxonomy("allergens") if a != "en:none"}
    allergens = resolve_allergens(ingredients, valid)
    counts = {"ingredients": 0, "with_allergen": 0, "skipped_no_english": 0, "skipped_additive": 0}
    for key, entry in ingredients.items():
        name = english_name(entry)
        if not name:
            counts["skipped_no_english"] += 1
            continue
        if "e_number" in entry:  # additives are seeded from additives.json
            counts["skipped_additive"] += 1
            continue
        ing_id = await upsert_ingredient(db, name, category="food_ingredient",
                                         description="Food ingredient (Open Food Facts taxonomy)")
        await add_function_fact(db, ing_id, source_id, parse_functions(entry))
        if key in allergens:
            await add_allergen_fact(db, ing_id, source_id, allergens[key])
            counts["with_allergen"] += 1
        counts["ingredients"] += 1
    return counts


async def seed_off():
    if not (OFF_DIR / "additives.json").exists():
        print(f"❌ Taxonomy files not found in {OFF_DIR}")
        return
    db = get_database()
    print("🚀 Starting Open Food Facts taxonomy seeding (English only)...")
    source_id = await upsert_source(db, **{k: SOURCE_METADATA[k] for k in
                                           ("name", "version", "license_type", "url", "attribution")})
    print(f"  📌 Source registered: {SOURCE_METADATA['name']} (ID: {source_id})")
    additives = await seed_additives(db, source_id)
    counts = await seed_ingredients(db, source_id)
    print(f"🎉 Open Food Facts seeding finished! additives: {additives} | {counts}")


if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await seed_off()
        await close_mongo_connection()

    asyncio.run(main())
