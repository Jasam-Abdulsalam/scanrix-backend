"""
Seeds India's FSSAI permitted-additive list as INFORMATION for food products.

Fact per additive: dimension 'permitted_regions', value 'india_fssai', severity 'none'. It only
says "named in FSSAI's additive tables"; it never raises a warning and never says anything about
additives that are NOT in the list (the extraction is positive-only and may be incomplete).

Input: data/curated/fssai_permitted_ins.json, produced once by scripts/extract_fssai.py.
Attached only to additives we already know (E-code ingredients seeded from Open Food Facts).
Reuse terms of the FSSAI document: to be confirmed at release.

Run: python -m scripts.seed_fssai [--dry-run]   (re-runs are safe: upserts, no duplicates)
Order: after seed_off (needs the E-code ingredients).
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import List

from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from scripts.common import find_ingredient_id, upsert_fact, upsert_source

INS_FILE = Path(__file__).resolve().parent.parent / "data" / "curated" / "fssai_permitted_ins.json"
SOURCE_META = {
    "name": "fssai_food_additives_appendix_a",
    "version": "Version 3 (01.08.2025)",
    "license_type": "FSSAI (reuse terms to be confirmed)",
    "url": "https://www.fssai.gov.in",
    "attribution": "FSSAI, Food Safety and Standards (Food Products Standards and Food Additives) Regulations, 2011, "
                   "Appendix A (compendium; informational, not a legal document)",
}
NOTE = ("Named in India's FSSAI food additive tables: permitted in certain foods, up to a maximum level. "
        "This is not a clearance for every food.")


def load_codes(path: Path = INS_FILE) -> List[str]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["ins_codes"]


def ingredient_key(ins_code: str) -> str:
    """INS '450vi' -> the matching form of the E-code ingredient 'e450vi'."""
    return "e" + ins_code.lower()


async def seed_fssai(db) -> Counter:
    source_id = await upsert_source(db, **SOURCE_META)
    stats: Counter = Counter()
    for code in load_codes():
        ing_id = await find_ingredient_id(db, ingredient_key(code))
        if not ing_id:
            stats["not_in_our_database"] += 1
            continue
        await upsert_fact(db, ing_id, source_id, "permitted_regions", "india_fssai", severity="none",
                          evidence_tier=1, verified=True, conditions=NOTE, applies_to="food")
        stats["marked_permitted_in_india"] += 1
    return stats


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        print(f"{len(load_codes())} INS codes would be matched against E-code ingredients")
        raise SystemExit

    async def main():
        await connect_to_mongo()
        print(f"🎉 FSSAI seeding finished! {dict(sorted((await seed_fssai(get_database())).items()))}")
        await close_mongo_connection()

    asyncio.run(main())
