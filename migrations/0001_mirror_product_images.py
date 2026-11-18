"""
Backfill: copy the photos of products saved before scans did it (app/services/product_image_mirror.py)
to Cloudinary, so the app stops loading them from Open Food/Beauty Facts' slow image servers.

Additive only: `image_url` is replaced by the Cloudinary copy, the original is kept in
`image_source_url`. A product whose copy fails keeps its original URL and is retried on the next run.
Idempotent: a copied product has `image_source_url`, so it no longer matches.

Run (inside the app container, Cloudinary keys must be set):
    docker compose exec app python -m migrations.0001_mirror_product_images [--dry-run] [--limit N]
"""
import argparse
import asyncio

from app.crud import crud_product
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.services import product_image_mirror

CONCURRENCY = 4  # parallel copies: gentle on Open Facts' servers and Cloudinary's rate limit


async def run(limit: int, dry_run: bool) -> tuple:
    """(copied, failed). O(n) in the products found, at most CONCURRENCY copies at a time."""
    todo = await crud_product.products_needing_image_mirror(limit)
    print(f"{len(todo)} product photos to copy")
    if dry_run or not todo:
        return 0, 0
    if not product_image_mirror.is_configured():
        raise SystemExit("Cloudinary keys are not set (CLOUDINARY_* in .env)")

    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(p: dict):
        async with gate:
            return await product_image_mirror.mirror_product_image(p["barcode"], p["image_url"])

    results = await asyncio.gather(*(one(p) for p in todo))
    copied = sum(1 for r in results if r)
    return copied, len(results) - copied


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only count")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    await connect_to_mongo()
    try:
        copied, failed = await run(args.limit, args.dry_run)
        print(f"copied {copied}, failed {failed} (failed ones keep their original URL; re-run to retry)")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
