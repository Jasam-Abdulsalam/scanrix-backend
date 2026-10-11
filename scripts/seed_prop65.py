import asyncio
import csv
import os
import re
from pathlib import Path
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database
from scripts.common import normalize_name, upsert_source, upsert_ingredient, upsert_alias, upsert_fact

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "p65chemicalslist.csv"

SOURCE_METADATA = {
    "name": "prop65",
    "version": "2026-07-31",
    "license_type": "State of California Public Records",
    "url": "https://oehha.ca.gov/proposition-65/proposition-65-list",
    "attribution": "Office of Environmental Health Hazard Assessment (OEHHA), California EPA"
}

def extract_parentheses_synonyms(text: str) -> list[str]:
    """
    Extracts synonyms inside parentheses, e.g.:
    '4-Aminobiphenyl (4-aminodiphenyl)' -> ['4-aminodiphenyl']
    """
    matches = re.findall(r"\((.*?)\)", text)
    synonyms = []
    for m in matches:
        cleaned = normalize_name(m)
        # Avoid short noise like single letters or abbreviations if too short
        if len(cleaned) > 2 and not cleaned.isdigit():
            synonyms.append(cleaned)
    return synonyms

async def seed_prop65():
    if not CSV_PATH.exists():
        print(f"❌ File not found at {CSV_PATH}")
        return

    db = get_database()
    print("🚀 Starting Proposition 65 Seeding...")

    # 1. Register Source
    source_id = await upsert_source(
        db,
        name=SOURCE_METADATA["name"],
        version=SOURCE_METADATA["version"],
        license_type=SOURCE_METADATA["license_type"],
        url=SOURCE_METADATA["url"],
        attribution=SOURCE_METADATA["attribution"]
    )
    print(f"  📌 Source registered: Prop 65 (ID: {source_id})")

    # 2. Parse CSV
    count_ingredients = 0
    count_facts = 0
    count_skipped_delisted = 0

    with open(CSV_PATH, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        
        # Skip intro header lines until the table header (row containing "Chemical")
        header_found = False
        for row in reader:
            if row and "chemical" in row[0].lower():
                header_found = True
                break
                
        if not header_found:
            print("❌ Could not find 'Chemical' header in CSV!")
            return

        for row in reader:
            if not row or len(row) < 4:
                continue

            raw_chemical = row[0].strip()
            raw_toxicity = row[1].strip().lower()
            raw_cas = row[3].strip()

            if not raw_chemical:
                continue

            # Skip delisted chemicals
            if "delisted" in raw_chemical.lower():
                count_skipped_delisted += 1
                continue

            # Clean name
            canonical_name = normalize_name(raw_chemical)
            if not canonical_name:
                continue

            # 3. Upsert Ingredient
            ingredient_id = await upsert_ingredient(
                db,
                canonical_name=canonical_name,
                cas_number=raw_cas,
                category="chemical",
                description="Listed under California Proposition 65"
            )
            count_ingredients += 1

            # 4. Extract and upsert any synonyms found in parentheses
            for syn in extract_parentheses_synonyms(raw_chemical):
                await upsert_alias(db, syn, ingredient_id, alias_type="synonym")

            # 5. Upsert Facts based on toxicity types
            # Possible toxicity values: 'cancer', 'developmental', 'female', 'male'
            toxicity_types = [t.strip() for t in raw_toxicity.split(",") if t.strip()]
            for tox in toxicity_types:
                if "cancer" in tox:
                    await upsert_fact(
                        db,
                        ingredient_id=ingredient_id,
                        source_id=source_id,
                        dimension="cancer_class",
                        value="listed_carcinogen",
                        severity="high",
                        evidence_tier=2,
                        verified=True
                    )
                    count_facts += 1
                elif "developmental" in tox:
                    await upsert_fact(
                        db,
                        ingredient_id=ingredient_id,
                        source_id=source_id,
                        dimension="developmental",
                        value="developmental_toxicity",
                        severity="high",
                        evidence_tier=2,
                        verified=True
                    )
                    count_facts += 1
                elif "male" in tox or "female" in tox or "reproductive" in tox:
                    await upsert_fact(
                        db,
                        ingredient_id=ingredient_id,
                        source_id=source_id,
                        dimension="reproductive",
                        value=f"reproductive_toxicity_{tox}",
                        severity="high",
                        evidence_tier=2,
                        verified=True
                    )
                    count_facts += 1

    print(f"🎉 Prop 65 Seeding Finished!")
    print(f"   • Ingredients processed: {count_ingredients}")
    print(f"   • Facts recorded: {count_facts}")
    print(f"   • Delisted/obsolete entries skipped: {count_skipped_delisted}")

if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await seed_prop65()
        await close_mongo_connection()

    asyncio.run(main())
