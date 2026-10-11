import asyncio
import csv
from pathlib import Path
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from scripts.common import normalize_name, upsert_source, upsert_ingredient, upsert_alias, upsert_fact

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "List of Classifications – IARC Monographs on the Identification of Carcinogenic Hazards to Humans.csv"

SOURCE_METADATA = {
    "name": "iarc",
    "version": "vol-138",
    "license_type": "World Health Organization (WHO) IARC Open Access",
    "url": "https://monographs.iarc.who.int/list-of-classifications",
    "attribution": "International Agency for Research on Cancer (IARC), World Health Organization"
}

IARC_SEVERITY_MAP = {
    "1": "critical",   # Carcinogenic to humans
    "2A": "high",      # Probably carcinogenic to humans
    "2B": "medium",    # Possibly carcinogenic to humans
    "3": "low"         # Not classifiable
}

async def seed_iarc():
    if not CSV_PATH.exists():
        print(f"❌ File not found at {CSV_PATH}")
        return

    db = get_database()
    print("🚀 Starting IARC Monographs Seeding...")

    # 1. Register Source
    source_id = await upsert_source(
        db,
        name=SOURCE_METADATA["name"],
        version=SOURCE_METADATA["version"],
        license_type=SOURCE_METADATA["license_type"],
        url=SOURCE_METADATA["url"],
        attribution=SOURCE_METADATA["attribution"]
    )
    print(f"  📌 Source registered: IARC (ID: {source_id})")

    count_ingredients = 0
    count_facts = 0

    with open(CSV_PATH, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)

        for row in reader:
            raw_cas = (row.get("CAS No.") or "").strip()
            raw_agent = (row.get("Agent") or "").strip()
            raw_group = (row.get("Group") or "").strip().upper()

            if not raw_agent or not raw_group:
                continue

            canonical_name = normalize_name(raw_agent)
            if not canonical_name:
                continue

            # Determine severity based on IARC classification
            severity = IARC_SEVERITY_MAP.get(raw_group, "medium")

            # 2. Upsert Ingredient
            ingredient_id = await upsert_ingredient(
                db,
                canonical_name=canonical_name,
                cas_number=raw_cas if raw_cas else None,
                category="chemical",
                description=f"Evaluated by IARC as Group {raw_group}"
            )
            count_ingredients += 1

            # 3. Upsert Fact
            await upsert_fact(
                db,
                ingredient_id=ingredient_id,
                source_id=source_id,
                dimension="cancer_class",
                value=f"Group {raw_group}",
                severity=severity,
                evidence_tier=2,
                verified=True
            )
            count_facts += 1

    print(f"🎉 IARC Seeding Finished!")
    print(f"   • Agents processed: {count_ingredients}")
    print(f"   • Facts recorded: {count_facts}")

if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await seed_iarc()
        await close_mongo_connection()

    asyncio.run(main())
