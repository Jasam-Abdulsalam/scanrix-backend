"""
One-off cleanup of products saved by the retired keyword fallback (ai_service._get_fallback_analysis).

That code stamped EVERY ingredient of a product with purpose "Common ingredient", a made-up
safety_rating and concerns such as "Contains trans fats" (it matched the substring "hydrogenated"
inside "non-hydrogenated"). Real verdicts come from the safety engine, so these fields were only wrong
noise. Affected ingredients are reset to the neutral shape the importers write today:
purpose None, safety_rating 50, concerns [] (name and is_natural are kept).

Run: python -m scripts.clean_legacy_ingredients [--dry-run]   (idempotent: a cleaned product no longer matches)
"""
import asyncio
import sys
from typing import Tuple

from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database

LEGACY_PURPOSE = "Common ingredient"
QUERY = {"ingredients.purpose": LEGACY_PURPOSE}


def clean_ingredients(ingredients: list) -> Tuple[list, int]:
    """(new list, how many ingredients were reset). Ingredients without the marker are untouched."""
    out, changed = [], 0
    for ing in ingredients:
        if isinstance(ing, dict) and ing.get("purpose") == LEGACY_PURPOSE:
            ing = {**ing, "purpose": None, "safety_rating": 50, "concerns": []}
            changed += 1
        out.append(ing)
    return out, changed


async def run(dry_run: bool) -> dict:
    db = get_database()
    products = ingredients = 0
    async for product in db.products.find(QUERY, {"ingredients": 1}):
        cleaned, changed = clean_ingredients(product.get("ingredients", []))
        products += 1
        ingredients += changed
        if not dry_run:
            await db.products.update_one({"_id": product["_id"]}, {"$set": {"ingredients": cleaned}})
    return {"products": products, "ingredients_reset": ingredients, "dry_run": dry_run}


if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        print(await run("--dry-run" in sys.argv))
        await close_mongo_connection()

    asyncio.run(main())
