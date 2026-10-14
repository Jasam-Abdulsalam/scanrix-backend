from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from pymongo.errors import DuplicateKeyError

from app.db.mongodb import get_database

RETENTION_WEEKS = 2  # old week documents are purged by a TTL index on expires_at


def current_week(now: Optional[datetime] = None) -> Tuple[str, datetime]:
    """(ISO week key like '2026-W42', the UTC moment the next week starts). Weeks start Monday 00:00 UTC."""
    now = now or datetime.now(timezone.utc)
    iso = now.isocalendar()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return f"{iso.year}-W{iso.week:02d}", monday + timedelta(days=7)


async def reserve(user_id: str, action: str, limit: int, now: Optional[datetime] = None) -> Optional[str]:
    """
    Atomically takes one credit. Returns the week key it was taken from, or None when the user has
    none left. One round trip, no read-then-write: the filter only matches while used < limit; when
    it does not match, the upsert tries to insert a second (user_id, week_key) document and the
    unique index raises DuplicateKeyError, which means "exhausted".
    """
    week_key, next_reset = current_week(now)
    try:
        await get_database().ai_credits.update_one(
            {"user_id": user_id, "week_key": week_key, "used": {"$lt": limit}},
            {
                "$inc": {"used": 1, f"by_action.{action}": 1},
                "$setOnInsert": {"expires_at": next_reset + timedelta(weeks=RETENTION_WEEKS)},
            },
            upsert=True,
        )
    except DuplicateKeyError:
        return None
    return week_key


async def refund(user_id: str, action: str, week_key: str) -> None:
    """Gives a credit back to the week it was taken from. Never goes below zero."""
    await get_database().ai_credits.update_one(
        {"user_id": user_id, "week_key": week_key, "used": {"$gt": 0}},
        {"$inc": {"used": -1, f"by_action.{action}": -1}},
    )


async def credits_used(user_id: str, now: Optional[datetime] = None) -> int:
    week_key, _ = current_week(now)
    doc = await get_database().ai_credits.find_one({"user_id": user_id, "week_key": week_key}, {"used": 1})
    return int(doc["used"]) if doc else 0
