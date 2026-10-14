"""
Prints the ingredient names scanned most often that our database does not recognise,
so you know which data to add first.

Run: python -m scripts.top_unknowns [--limit 50] [--category food|cosmetic]
"""
import argparse
import asyncio

from app.crud.crud_unknown_ingredient import top_unknown_ingredients
from app.db.mongodb import close_mongo_connection, connect_to_mongo


async def main(limit: int, category: str | None):
    await connect_to_mongo()
    rows = await top_unknown_ingredients(limit, category)
    print(f"{'scans':>6}  {'category':<10}  name")
    for row in rows:
        print(f"{row['scan_count']:>6}  {row['category']:<10}  {row['name']}")
    if not rows:
        print("(nothing recorded yet: scan some products first)")
    await close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--category", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.category))
