"""
Seeds the EU CosIng annexes (II-VI) from data/raw/cosing/annex_<N>.csv.

Every fact is stored with applies_to='cosmetic', so the engine ignores it for food products.

Policy (agreed 2026-10-13):
- IV colourants / V preservatives / VI UV filters: recognised + 'function' fact with the conditions
  text. Permissions, never warnings.
- III restricted: low-severity 'Restricted in EU cosmetics' ONLY when the row has no product type
  (a general restriction). Rows naming a product type (hair dye, oral, leave-on...) are information
  only, because we cannot tell which kind of product was scanned.
- II prohibited: critical 'prohibited' ONLY when the name has no use qualifier ("when used in hair
  dye...", "except..."). Qualified rows are information only. Matched by CAS number first.
- Wording stays "listed/restricted in the EU Cosmetics Regulation": CosIng has no legal value.

Source: European Commission CosIng, https://ec.europa.eu/growth/tools-databases/cosing/
Reuse terms: NOT yet confirmed. Read the site's legal notice before publishing.

Run: python -m scripts.seed_cosing [--dry-run]   (re-runs are safe: upserts, no duplicates)
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

COSING_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "cosing"
SOURCE_VERSION = "2026-10-13"  # file creation date in the CSV header
FUNCTIONS = {"IV": "colourant", "V": "preservative", "VI": "UV filter"}
MAX_CANONICAL_LEN = 100  # longer chemical names are skipped: they would never appear on a label
MAX_CONDITIONS_LEN = 500
CAS_PATTERN = re.compile(r"\d{2,7}-\d{2}-\d")
USE_QUALIFIER = re.compile(r"\b(when|except|only|other than|used as|hair)\b", re.IGNORECASE)
NAME_SEPARATOR = re.compile(r"\s+/\s+|/\s+|;\s*")  # " / ", "CI 42053/ NAME", ";" (not PEG/PPG-17)
NAME_COLUMNS = ("Name of Common Ingredients Glossary", "Colour index Number / Name of Common Ingredients Glossary")


def load_annex(annex: str, directory: Path = COSING_DIR) -> List[Dict[str, str]]:
    """Rows as dicts. Skips the metadata lines above the real header row."""
    with open(directory / f"annex_{annex}.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    start = next(i for i, r in enumerate(rows) if r and r[0] == "Reference Number")
    return [dict(zip(rows[start], r)) for r in rows[start + 1:] if r and r[0].strip()]


def matching_form(text: str) -> str:
    """Same normalisation the parser applies to label text, so stored names can match."""
    return ingredient_parser.normalize_ingredient_token(text)


def split_names(text: str) -> List[str]:
    names = (matching_form(n) for n in NAME_SEPARATOR.split(text or ""))
    return list(dict.fromkeys(n for n in names if n))


def split_cas(text: str) -> List[str]:
    return CAS_PATTERN.findall(text or "")


def clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xad", "")).strip()


def conditions_text(row: Dict[str, str]) -> str:
    parts = [
        ("Product type", row.get("Product Type, body parts")),
        ("Max concentration", row.get("Maximum concentration in ready for use preparation")),
        ("Other", row.get("Other")),
        ("Warnings", row.get("Wording of conditions of use and warnings")),
    ]
    text = "; ".join(f"{label}: {clean(v)}" for label, v in parts if clean(v))
    return text[:MAX_CONDITIONS_LEN]


def fact_for(annex: str, row: Dict[str, str]) -> Optional[dict]:
    """The single fact this row contributes (dimension, value, severity), or None."""
    cond = conditions_text(row)
    if annex in FUNCTIONS:
        return {"dimension": "function", "value": FUNCTIONS[annex], "severity": "none", "conditions": cond}
    if annex == "III":
        general = not clean(row.get("Product Type, body parts"))
        return {"dimension": "regulatory", "severity": "low" if general else "none", "conditions": cond,
                "value": "cosmetics_restricted_eu" if general else "cosmetics_restricted_in_specific_use_eu"}
    qualified = bool(USE_QUALIFIER.search(row.get("Chemical name / INN", "")))
    return {"dimension": "regulatory", "severity": "none" if qualified else "critical",
            "value": "cosmetics_banned_in_specific_use_eu" if qualified else "cosmetics_banned_eu",
            "conditions": clean(row.get("Chemical name / INN"))[:MAX_CONDITIONS_LEN] if qualified else None}


def names_for(annex: str, row: Dict[str, str]) -> List[str]:
    if annex == "II":
        name = matching_form(row.get("Chemical name / INN", ""))
        return [name] if name and len(name) <= MAX_CANONICAL_LEN else []
    column = next((c for c in NAME_COLUMNS if c in row), "")
    return split_names(row.get(column, ""))


async def resolve_ingredient(db, annex: str, name: str, cas: List[str]) -> Optional[str]:
    """Existing ingredient (by CAS first for Annex II, then by name alias) or a new one."""
    for number in cas if annex == "II" else []:
        found = await find_ingredient_id(db, number)
        if found:
            return found
    found = await find_ingredient_id(db, name)
    if found:
        return found
    return await upsert_ingredient(db, name, cas_number=cas[0] if len(cas) == 1 else None,
                                   category="cosmetic_ingredient", description="Listed in the EU CosIng annexes")


async def seed_annex(db, annex: str, stats: Counter):
    meta = {"name": f"cosing_annex_{annex.lower()}", "version": SOURCE_VERSION,
            "license_type": "European Commission CosIng (reuse terms to be confirmed)",
            "url": "https://ec.europa.eu/growth/tools-databases/cosing/",
            "attribution": f"European Commission, CosIng database, Annex {annex} (informational, no legal value)"}
    source_id = await upsert_source(db, **meta)
    seen = set()
    for row in load_annex(annex):
        fact, cas = fact_for(annex, row), split_cas(row.get("CAS Number"))
        for name in names_for(annex, row):
            ing_id = await resolve_ingredient(db, annex, name, cas)
            if not ing_id or ing_id in seen:  # first row wins per ingredient and annex
                stats[f"{annex}_skipped"] += 1
                continue
            seen.add(ing_id)
            for number in cas if len(names_for(annex, row)) == 1 else []:
                await link_alias(db, number, ing_id)
            await upsert_fact(db, ing_id, source_id, fact["dimension"], fact["value"], severity=fact["severity"],
                              evidence_tier=1, verified=True, conditions=fact["conditions"],
                              applies_to="cosmetic")
            stats[f"{annex}_{fact['severity']}"] += 1


def dry_run():
    for annex in ("II", "III", "IV", "V", "VI"):
        rows = load_annex(annex)
        facts = Counter(f"{(fact_for(annex, r) or {}).get('dimension')}/{(fact_for(annex, r) or {}).get('severity')}" for r in rows)
        names = sum(len(names_for(annex, r)) for r in rows)
        print(f"Annex {annex}: {len(rows)} rows -> {names} names | facts: {dict(facts)}")


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        dry_run()
        raise SystemExit

    async def main():
        await connect_to_mongo()
        stats: Counter = Counter()
        for annex in ("II", "III", "IV", "V", "VI"):
            await seed_annex(get_database(), annex, stats)
        print(f"🎉 CosIng seeding finished! {dict(sorted(stats.items()))}")
        await close_mongo_connection()

    asyncio.run(main())
