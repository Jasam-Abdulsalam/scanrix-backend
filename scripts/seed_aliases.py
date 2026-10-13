"""
Loads hand-checked aliases from data/curated/aliases.json onto EXISTING ingredients.

Names only: it never creates ingredients, facts or warnings. A target that does not
exist is reported and skipped; an alias that already points to another ingredient is
reported as a conflict and left untouched. Re-runs are safe.

Run: python -m scripts.seed_aliases
"""
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.services.ingredient_parser import ingredient_parser
from scripts.common import link_alias

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "curated" / "aliases.json"


def matching_form(alias: str) -> str:
    """The exact normalisation the parser applies to label text, so stored aliases can match."""
    return ingredient_parser.normalize_ingredient_token(alias)


def load_entries(path: Path = CURATED_PATH) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["entries"]


def validate_entries(entries: List[dict]) -> List[Tuple[str, List[str]]]:
    """Returns [(canonical, [aliases in matching form])]. Raises ValueError on an empty alias
    or an alias listed under two different ingredients (which one wins would be ambiguous)."""
    seen: Dict[str, str] = {}
    result = []
    for entry in entries:
        canonical = entry["canonical"]
        forms = []
        for alias in entry["aliases"]:
            form = matching_form(alias)
            if not form:
                raise ValueError(f"Empty alias under {canonical!r}: {alias!r}")
            if seen.get(form, canonical) != canonical:
                raise ValueError(f"Alias {form!r} is listed under both {seen[form]!r} and {canonical!r}")
            seen[form] = canonical
            forms.append(form)
        result.append((canonical, forms))
    return result


async def seed_aliases():
    db = get_database()
    totals: Counter = Counter()
    missing: List[str] = []
    print("🚀 Loading curated aliases...")
    for canonical, aliases in validate_entries(load_entries()):
        ingredient = await db.ingredients.find_one({"canonical_name": canonical})
        if ingredient is None:
            missing.append(canonical)
            continue
        for alias in aliases:
            totals[await link_alias(db, alias, str(ingredient["_id"]))] += 1
    print(f"🎉 Curated aliases finished! {dict(totals)}")
    if missing:
        print(f"⚠️ Target ingredient not found (skipped): {missing}")
    if totals["conflict"]:
        print("⚠️ Some aliases already point to a different ingredient and were left untouched.")


if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await seed_aliases()
        await close_mongo_connection()

    asyncio.run(main())
