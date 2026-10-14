import asyncio
import sys
from pymongo import ASCENDING
from app.db.mongodb import connect_to_mongo, close_mongo_connection, get_database

async def create_indexes(db=None):
    """
    Ensures all required indexes exist in MongoDB Atlas.
    Safe to run repeatedly — MongoDB creates them if missing, or skips if they already exist.
    """
    if db is None:
        db = get_database()

    print("🔧 Ensuring MongoDB indexes for Ingredient Safety Engine...")

    # 1. Sources Collection
    # Prevents adding the same source snapshot version multiple times
    await db.sources.create_index(
        [("name", ASCENDING), ("version", ASCENDING)],
        unique=True,
        name="unique_source_name_version"
    )
    print("  ✅ sources: index on (name, version) [unique]")

    # 2. Ingredients Collection (The Master Canonical Records)
    # Fast lookup by canonical name; sparse index on CAS number
    await db.ingredients.create_index(
        [("canonical_name", ASCENDING)],
        unique=True,
        name="unique_canonical_name"
    )
    await db.ingredients.create_index(
        [("cas_number", ASCENDING)],
        sparse=True,
        name="sparse_cas_number"
    )
    print("  ✅ ingredients: indexes on canonical_name [unique] and cas_number [sparse]")

    # 3. Aliases Collection (Packaging / Trade names / E-numbers)
    # UNIQUE on normalized_alias guarantees 1 alias string maps to exactly 1 ingredient
    await db.aliases.create_index(
        [("normalized_alias", ASCENDING)],
        unique=True,
        name="unique_normalized_alias"
    )
    await db.aliases.create_index(
        [("ingredient_id", ASCENDING)],
        name="idx_alias_ingredient_id"
    )
    print("  ✅ aliases: indexes on normalized_alias [unique] and ingredient_id")

    # 4. Facts Collection (Scientific / Regulatory findings)
    # Fast query: get all facts for an ingredient, or facts for a specific dimension
    await db.facts.create_index(
        [("ingredient_id", ASCENDING)],
        name="idx_fact_ingredient_id"
    )
    await db.facts.create_index(
        [("ingredient_id", ASCENDING), ("dimension", ASCENDING)],
        name="idx_fact_ingredient_dimension"
    )
    # Compound unique index to prevent duplicate fact insertions from the same source
    await db.facts.create_index(
        [("ingredient_id", ASCENDING), ("source_id", ASCENDING), ("dimension", ASCENDING)],
        unique=True,
        name="unique_fact_per_source_dimension"
    )
    print("  ✅ facts: indexes on (ingredient_id, dimension) and unique per (ingredient_id, source_id, dimension)")

    # 5. AI Review Queue
    # Filter pending AI-generated proposals for human verification
    await db.ai_review_queue.create_index(
        [("status", ASCENDING)],
        name="idx_review_status"
    )
    print("  ✅ ai_review_queue: index on status")

    # 6. Unknown ingredients (scan counter)
    # unique (name, category): the upsert filter in record_unknown_ingredients
    await db.unknown_ingredients.create_index(
        [("name", ASCENDING), ("category", ASCENDING)],
        unique=True,
        name="unique_unknown_name_category"
    )
    # scripts.top_unknowns sorts by scan_count descending
    await db.unknown_ingredients.create_index(
        [("scan_count", -1)],
        name="idx_unknown_scan_count"
    )
    print("  ✅ unknown_ingredients: unique (name, category) and scan_count")

    print("🎉 All database indexes successfully verified/created!")

if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await create_indexes()
        await close_mongo_connection()

    asyncio.run(main())
