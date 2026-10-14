"""
Seeds "known health effects" from ECHA's table of harmonised entries (CLP Annex VI, ATP23).

Policy (agreed approach, 2026-10-14):
- INFORMATION ONLY: severity 'none', so these facts can never change a score or verdict. The
  classification describes the pure, undiluted substance; the concentration in a product decides
  the real risk (citric acid is listed as an eye irritant, yet fine in food).
- Only health effects a shopper can relate to (skin/eye irritation, allergy, cancer, ...). Physical
  (flammable...) and environmental hazards are ignored.
- Facts are attached ONLY to ingredients we already know (matched by CAS number, then by name).
  No industrial chemicals are created.
- applies_to='cosmetic' for now (food would need its own wording).
- Entries whose application date is still in the future are skipped (not legally applicable yet).

Source file: https://echa.europa.eu/information-on-chemicals/annex-vi-to-clp (unofficial Excel; the
Official Journal text is the only legally binding version). Reuse terms: to be confirmed at release.

Run: python -m scripts.seed_echa_clp [--dry-run]   (re-runs are safe: upserts, no duplicates)
"""
import asyncio
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from app.services.ingredient_parser import ingredient_parser
from scripts.common import find_ingredient_id, upsert_fact, upsert_source
from scripts.xlsx_reader import read_sheet

ECHA_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "echa" / "annex_vi_clp_table_atp23_en.xlsx"
HEADER_ROW = 3  # rows 1-2 hold the disclaimer
SOURCE_META = {
    "name": "echa_clp_annex_vi",
    "version": "ATP23",
    "license_type": "ECHA (reuse terms to be confirmed)",
    "url": "https://echa.europa.eu/information-on-chemicals/annex-vi-to-clp",
    "attribution": "ECHA, CLP Annex VI harmonised classification (ATP23); informational, not legally binding",
}
CAS_PATTERN = re.compile(r"\d{2,7}-\d{2}-\d")
H_CODE = re.compile(r"H\d{3}")
EXCEL_EPOCH = date(1899, 12, 30)

# base H-code -> (effect key, plain-English sentence about the pure substance)
EFFECTS = {
    "H314": ("corrosive", "Can cause severe skin burns and eye damage"),
    "H315": ("skin_irritation", "Can irritate the skin"),
    "H317": ("skin_allergy", "May cause an allergic skin reaction"),
    "H318": ("eye_damage", "Can cause serious eye damage"),
    "H319": ("eye_irritation", "Can irritate the eyes"),
    "H334": ("respiratory_allergy", "May cause allergy or breathing difficulties if inhaled"),
    "H335": ("respiratory_irritation", "May irritate the airways"),
    "H340": ("mutagenic", "May cause genetic defects"),
    "H341": ("mutagenic_suspected", "Suspected of causing genetic defects"),
    "H350": ("carcinogenic", "May cause cancer"),
    "H351": ("carcinogenic_suspected", "Suspected of causing cancer"),
    "H360": ("reproductive", "May damage fertility or the unborn child"),
    "H361": ("reproductive_suspected", "Suspected of damaging fertility or the unborn child"),
    "H370": ("organ_damage", "Causes damage to organs"),
    "H372": ("organ_damage", "Causes damage to organs through prolonged exposure"),
    "H371": ("organ_damage_suspected", "May cause damage to organs"),
    "H373": ("organ_damage_suspected", "May cause damage to organs through prolonged exposure"),
    "H300": ("toxic_swallowed", "Fatal or toxic if swallowed"), "H301": ("toxic_swallowed", "Fatal or toxic if swallowed"),
    "H310": ("toxic_skin", "Fatal or toxic in contact with skin"), "H311": ("toxic_skin", "Fatal or toxic in contact with skin"),
    "H330": ("toxic_inhaled", "Fatal or toxic if inhaled"), "H331": ("toxic_inhaled", "Fatal or toxic if inhaled"),
    "H302": ("harmful_swallowed", "Harmful if swallowed"),
    "H312": ("harmful_skin", "Harmful in contact with skin"),
    "H332": ("harmful_inhaled", "Harmful if inhaled"),
}


def effects_from_codes(codes: str) -> Set[str]:
    """'H315\\nH360FD' -> {'skin_irritation', 'reproductive'}. Unlisted (physical/environmental) codes are dropped."""
    return {EFFECTS[c][0] for c in H_CODE.findall(codes or "") if c in EFFECTS}


def describe(keys: Set[str]) -> str:
    sentences = {text for key, text in EFFECTS.values() if key in keys}
    return "; ".join(sorted(sentences))


def is_in_force(row: Dict[str, str], today: Optional[date] = None) -> bool:
    """'In application' is an Excel date serial. Blank or unparsable is treated as in force."""
    raw = row.get("In application", "")
    try:
        applies = EXCEL_EPOCH + timedelta(days=int(float(raw)))
    except ValueError:
        return True
    return applies <= (today or date.today())


def load_entries() -> List[Dict[str, str]]:
    return read_sheet(ECHA_FILE, "xl/worksheets/sheet1.xml", HEADER_ROW)


def entry_names(row: Dict[str, str]) -> List[str]:
    """Substance names of one entry. Multi-substance entries hold one per line ('boric acid [1]'),
    and synonyms are separated by ';'. Returns names in matching form."""
    parts = re.split(r"[\n;]", row.get("Chemical Name", ""))
    names = (ingredient_parser.normalize_ingredient_token(re.sub(r"\[\d+\]", "", p)) for p in parts)
    return list(dict.fromkeys(n for n in names if n))


async def resolve_known_ingredients(db, row: Dict[str, str]) -> Set[str]:
    """Existing ingredients named by an entry (by CAS number, then by name). Never creates one."""
    ids: Set[str] = set()
    for key in CAS_PATTERN.findall(row.get("CAS No", "")) + entry_names(row):
        found = await find_ingredient_id(db, key)
        if found:
            ids.add(found)
    return ids


async def collect_effects(db, entries: List[Dict[str, str]], stats: Counter) -> Dict[str, Set[str]]:
    """Ingredient id -> union of effect keys over all its entries."""
    found: Dict[str, Set[str]] = defaultdict(set)
    for row in entries:
        keys = effects_from_codes(row.get("Classification Hazard Statement Code(s)", ""))
        if not keys or not is_in_force(row):
            stats["skipped_no_health_effect_or_not_in_force"] += 1
            continue
        ids = await resolve_known_ingredients(db, row)
        stats["entries_matched" if ids else "entries_not_in_our_database"] += 1
        for ing_id in ids:
            found[ing_id] |= keys
    return found


async def seed_echa(db) -> Counter:
    stats: Counter = Counter()
    source_id = await upsert_source(db, **SOURCE_META)
    for ing_id, keys in (await collect_effects(db, load_entries(), stats)).items():
        await upsert_fact(db, ing_id, source_id, "health_effects", ",".join(sorted(keys)), severity="none",
                          evidence_tier=1, verified=True, conditions=describe(keys), applies_to="cosmetic")
        stats["ingredients_with_effects"] += 1
    return stats


def dry_run():
    entries = load_entries()
    usable = [r for r in entries if effects_from_codes(r.get("Classification Hazard Statement Code(s)", "")) and is_in_force(r)]
    print(f"{len(entries)} entries | {len(usable)} with a health effect that is in force")


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        dry_run()
        raise SystemExit

    async def main():
        await connect_to_mongo()
        print(f"🎉 ECHA CLP seeding finished! {dict(sorted((await seed_echa(get_database())).items()))}")
        await close_mongo_connection()

    asyncio.run(main())
