"""
Seeds the EU Inventory of Cosmetic Ingredients (Commission Decision 2006/257/EC) as RECOGNITION data.

It says what a cosmetic ingredient is and what it is used for (glycerin: humectant, solvent).
It contains NO hazard information, so it never raises a warning:
- one 'function' fact per ingredient (severity 'none', applies_to 'cosmetic')
- the 'Restriction' column is ignored on purpose: restrictions come from the CosIng annexes (seed_cosing)

Source file: Zenodo record 3959386 (EUCOSMETICS_Decision_96-335-EC_all.csv), licence CC-BY-4.0,
curated by R. Aalizadeh (Univ. of Athens) from the Commission's inventory. The 2006 inventory is
old: newer ingredients may be missing (they stay "not assessed").

Run: python -m scripts.seed_eu_inventory [--dry-run]   (re-runs are safe: upserts, no duplicates)
Order: run after seed_aliases and seed_cosing so existing ingredients are reused, not duplicated.
"""
import asyncio
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.services.ingredient_parser import ingredient_parser
from scripts.common import find_ingredient_id, link_alias, upsert_fact, upsert_ingredient, upsert_source

INVENTORY_FILE = (Path(__file__).resolve().parent.parent / "data" / "raw" / "eu_inventory"
                  / "EUCOSMETICS_Decision_96-335-EC_all.csv")
SOURCE_META = {
    "name": "eu_cosmetic_inventory_2006",
    "version": "Decision 2006/257/EC (Zenodo 3959386)",
    "license_type": "CC-BY-4.0",
    "url": "https://zenodo.org/records/3959386",
    "attribution": ("EU Inventory of Cosmetic Ingredients (Decision 2006/257/EC), curated by R. Aalizadeh, "
                    "University of Athens, via Zenodo (CC-BY-4.0). Informational, no legal value"),
}
INFO_TIER = 2
MAX_NAME_LEN = 100
CAS_PATTERN = re.compile(r"\d{2,7}-\d{2}-\d")


def load_inventory(path: Path = INVENTORY_FILE) -> List[Dict[str, str]]:
    with open(path, encoding="cp1252", newline="") as f:  # the file is Windows-1252, not UTF-8
        return list(csv.DictReader(f))


def inventory_name(row: Dict[str, str]) -> str:
    """Same normalisation the parser applies to label text, so the stored name can match."""
    name = ingredient_parser.normalize_ingredient_token(row.get("INCI name", ""))
    return name if len(name) <= MAX_NAME_LEN else ""


def parse_functions(text: str) -> List[str]:
    """'Emulsifying/ skin conditioning' -> ['emulsifying', 'skin conditioning'] (lower-case, de-duplicated)."""
    parts = (re.sub(r"\s+", " ", p).strip().lower() for p in (text or "").split("/"))
    return list(dict.fromkeys(p for p in parts if p))


def cas_numbers(row: Dict[str, str]) -> List[str]:
    return CAS_PATTERN.findall(row.get("CAS No", "") or "")


def unique_cas_owners(rows: List[Dict[str, str]]) -> Dict[str, str]:
    """CAS -> INCI name, only for CAS numbers used by exactly ONE name. Shared CAS numbers
    (e.g. a plant's extract and its oil) must not point at an arbitrary one of them. O(rows)."""
    owners: Dict[str, set] = {}
    for row in rows:
        name = inventory_name(row)
        for cas in cas_numbers(row):
            owners.setdefault(cas, set()).add(name)
    return {cas: next(iter(names)) for cas, names in owners.items() if len(names) == 1 and "" not in names}


async def seed_row(db, source_id: str, row: Dict[str, str], cas_owner: Dict[str, str], stats: Counter):
    name = inventory_name(row)
    if not name:
        stats["skipped_no_name"] += 1
        return
    own_cas = [c for c in cas_numbers(row) if cas_owner.get(c) == name]
    ing_id = await find_ingredient_id(db, name)
    stats["reused" if ing_id else "created"] += 1
    if not ing_id:
        ing_id = await upsert_ingredient(db, name, cas_number=own_cas[0] if len(own_cas) == 1 else None,
                                         category="cosmetic_ingredient",
                                         description="Listed in the EU Inventory of Cosmetic Ingredients")
    for cas in own_cas:
        await link_alias(db, cas, ing_id)
    functions = parse_functions(row.get("Function", ""))
    if functions:
        await upsert_fact(db, ing_id, source_id, "function", ", ".join(functions), severity="none",
                          evidence_tier=INFO_TIER, verified=False, applies_to="cosmetic")
        stats["function_facts"] += 1


async def seed_inventory(db) -> Counter:
    rows = load_inventory()
    cas_owner = unique_cas_owners(rows)
    source_id = await upsert_source(db, **SOURCE_META)
    stats: Counter = Counter()
    for row in rows:
        await seed_row(db, source_id, row, cas_owner, stats)
    return stats


def dry_run():
    rows = load_inventory()
    names = [inventory_name(r) for r in rows]
    with_function = sum(1 for r in rows if parse_functions(r.get("Function", "")))
    print(f"{len(rows)} rows | {len(set(n for n in names if n))} distinct names | "
          f"{with_function} with a function | {len(unique_cas_owners(rows))} CAS numbers owned by one name")


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        dry_run()
        raise SystemExit

    async def main():
        await connect_to_mongo()
        stats = await seed_inventory(get_database())
        print(f"🎉 EU cosmetic inventory seeding finished! {dict(sorted(stats.items()))}")
        await close_mongo_connection()

    asyncio.run(main())
