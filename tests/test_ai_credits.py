import asyncio
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.crud import crud_ai_credits as crud
from app.services import credits_service as svc


class FakeCreditsCollection:
    """Mimics the parts of Mongo the credits code relies on: $lt filter + upsert + unique (user, week)."""
    def __init__(self):
        self.docs = {}

    async def update_one(self, filt, update, upsert=False):
        key = (filt["user_id"], filt["week_key"])
        doc = self.docs.get(key)
        if "used" in filt and "$lt" in filt["used"]:           # reserve
            if doc is None:
                self.docs[key] = {"used": 1, "by_action": {}}
                doc = self.docs[key]
            elif doc["used"] < filt["used"]["$lt"]:
                doc["used"] += 1
            else:
                raise DuplicateKeyError("E11000 duplicate key")  # filter missed, upsert hit the unique index
            for path, n in update["$inc"].items():
                if path.startswith("by_action."):
                    action = path.split(".", 1)[1]
                    doc["by_action"][action] = doc["by_action"].get(action, 0) + n
        elif doc is not None and doc["used"] > filt["used"]["$gt"]:  # refund
            doc["used"] += update["$inc"]["used"]
            for path, n in update["$inc"].items():
                if path.startswith("by_action."):
                    doc["by_action"][path.split(".", 1)[1]] += n

    async def find_one(self, filt, projection=None):
        return self.docs.get((filt["user_id"], filt["week_key"]))


class FakeDb:
    def __init__(self):
        self.ai_credits = FakeCreditsCollection()


def setup(monkeypatch, limit=3):
    db = FakeDb()
    monkeypatch.setattr(crud, "get_database", lambda: db)
    monkeypatch.setattr(svc.settings, "AI_CREDITS_PER_WEEK", limit)
    return db


WED = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def test_week_key_and_reset_time_are_monday_midnight_utc():
    key, reset = crud.current_week(WED)
    assert key == "2026-W42" and reset == datetime(2026, 10, 19, tzinfo=timezone.utc)
    sunday_late = datetime(2026, 10, 18, 23, 59, tzinfo=timezone.utc)
    monday_early = datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)
    assert crud.current_week(sunday_late)[0] == "2026-W42" and crud.current_week(monday_early)[0] == "2026-W43"


def test_credits_stop_at_the_limit_and_count_by_action(monkeypatch):
    db = setup(monkeypatch, limit=3)
    for _ in range(3):
        assert asyncio.run(svc.reserve_credit("u1", "ai_verdict")).week_key
    try:
        asyncio.run(svc.reserve_credit("u1", "ai_verdict"))
        assert False, "fourth reservation must fail"
    except svc.CreditsExhausted as e:
        assert e.resets_at.weekday() == 0 and e.resets_at.hour == 0  # next Monday 00:00 UTC
    assert next(iter(db.ai_credits.docs.values()))["by_action"] == {"ai_verdict": 3}
    assert asyncio.run(svc.reserve_credit("u2", "ai_verdict")).user_id == "u2"  # other users unaffected


def test_refund_gives_the_credit_back_and_never_goes_below_zero(monkeypatch):
    setup(monkeypatch, limit=2)
    r = asyncio.run(svc.reserve_credit("u1", "ai_verdict"))
    assert asyncio.run(svc.get_balance("u1")).remaining == 1
    asyncio.run(svc.refund_credit(r))
    assert asyncio.run(svc.get_balance("u1")).remaining == 2
    asyncio.run(svc.refund_credit(r))  # double refund: ignored
    assert asyncio.run(svc.get_balance("u1")).remaining == 2


def test_balance_reports_limit_remaining_and_next_reset(monkeypatch):
    setup(monkeypatch, limit=6)
    asyncio.run(svc.reserve_credit("u1", "view_alternatives"))  # another future action shares the pool
    balance = asyncio.run(svc.get_balance("u1"))
    assert (balance.limit, balance.remaining) == (6, 5) and balance.resets_at.weekday() == 0
