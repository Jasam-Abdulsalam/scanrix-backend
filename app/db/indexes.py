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

    # 7. AI credits: one document per (user, ISO week); the unique index is what makes reserve() atomic
    await db.ai_credits.create_index(
        [("user_id", ASCENDING), ("week_key", ASCENDING)],
        unique=True,
        name="unique_ai_credits_user_week"
    )
    # TTL: purge old weeks (expires_at is set on insert)
    await db.ai_credits.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="ttl_ai_credits_expires_at"
    )
    print("  ✅ ai_credits: unique (user_id, week_key) + TTL on expires_at")

    # 8. AI product analyses cache: looked up by cache_key; TTL is the invalidation strategy
    await db.ai_product_analyses.create_index(
        [("cache_key", ASCENDING)],
        unique=True,
        name="unique_ai_analysis_cache_key"
    )
    await db.ai_product_analyses.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="ttl_ai_analysis_expires_at"
    )
    print("  ✅ ai_product_analyses: unique cache_key + TTL on expires_at")

    # 9. Scan history list: user's entries newest first, cursor pagination (user_id = prefix of the sort)
    await db.scan_history.create_index(
        [("user_id", ASCENDING), ("scanned_at", -1), ("_id", -1)],
        name="idx_history_user_scanned"
    )
    print("  ✅ scan_history: (user_id, scanned_at desc, _id desc)")

    # 10. Favorites: unique per (user, product) makes "add" idempotent and race-safe;
    # the second index serves the paginated list (newest first) and the barcodes projection.
    await db.favorites.create_index(
        [("user_id", ASCENDING), ("product_id", ASCENDING)],
        unique=True,
        name="unique_favorite_user_product"
    )
    await db.favorites.create_index(
        [("user_id", ASCENDING), ("created_at", -1), ("_id", -1)],
        name="idx_favorites_user_created"
    )
    print("  ✅ favorites: unique (user_id, product_id) + (user_id, created_at desc, _id desc)")

    print("🎉 All database indexes successfully verified/created!")

if __name__ == "__main__":
    async def main():
        await connect_to_mongo()
        await create_indexes()
        await close_mongo_connection()

    asyncio.run(main())
