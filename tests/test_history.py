import asyncio
from datetime import datetime, timedelta

import httpx
from bson import ObjectId
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1.endpoints.history import router
from app.core.pagination import encode_cursor
from app.crud import crud_history, crud_product
from tests.fake_mongo import FakeCollection

ME, OTHER = ObjectId(), ObjectId()
T0 = datetime(2026, 10, 1, 12, 0)


class FakeDb:
    def __init__(self, history, products):
        self.scan_history = FakeCollection(history)
        self.products = FakeCollection(products)


def _entry(user, product_id, minutes, verdict="safe"):
    return {"_id": ObjectId(), "user_id": user, "product_id": product_id, "verdict": verdict,
            "personalized_score": None, "scanned_at": T0 + timedelta(minutes=minutes)}


def _product(name):
    return {"_id": ObjectId(), "barcode": f"b-{name}", "name": name, "brand": "Brand", "category": "food",
            "image_url": f"http://img/{name}.png"}


def setup(monkeypatch, user=ME):
    p1, p2 = _product("one"), _product("two")
    gone = ObjectId()  # a product that was deleted
    entries = [_entry(ME, p1["_id"], 1), _entry(ME, p2["_id"], 2, "avoid"), _entry(ME, gone, 3),
               _entry(OTHER, p1["_id"], 4)]
    db = FakeDb(entries, [p1, p2])
    monkeypatch.setattr(crud_history, "get_database", lambda: db)
    monkeypatch.setattr(crud_product, "get_database", lambda: db)
    app = FastAPI()
    app.include_router(router, prefix="/history")
    app.dependency_overrides[get_current_user] = lambda: {"_id": user}
    return app, db, entries


def call(app, method, path):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.request(method, path)
    return asyncio.run(go())


def test_first_page_is_newest_first_with_product_summary_and_only_mine(monkeypatch):
    app, db, _ = setup(monkeypatch)
    r = call(app, "GET", "/history/")
    assert r.status_code == 200
    body = r.json()
    rows = body["items"]
    assert len(rows) == 3                                   # the other user's entry is not included
    assert [x["scanned_at"] for x in rows] == sorted((x["scanned_at"] for x in rows), reverse=True)
    assert rows[1]["product"] == {"barcode": "b-two", "name": "two", "brand": "Brand",
                                  "category": "food", "image_url": "http://img/two.png"}
    assert rows[0]["product"] is None                       # deleted product: row still returned
    assert db.products.find_calls == 1                      # batched, not one query per row
    assert body["has_more"] is False and body["next_cursor"] is None


def test_pages_walk_the_whole_list_with_no_gaps_or_repeats(monkeypatch):
    app, db, _ = setup(monkeypatch)
    pid = ObjectId()
    same_time = T0 + timedelta(minutes=5)                # ties straddle a page boundary: _id must break them
    db.scan_history.docs[:] = [_entry(ME, pid, m) for m in range(10)]
    db.scan_history.docs += [{**_entry(ME, pid, 0), "scanned_at": same_time} for _ in range(4)]
    seen, cursor, pages = [], None, 0
    while True:
        url = "/history/?limit=4" + (f"&cursor={cursor}" if cursor else "")
        body = call(app, "GET", url).json()
        seen += [x["id"] for x in body["items"]]
        pages += 1
        assert len(body["items"]) <= 4
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        cursor = body["next_cursor"]
    assert pages == 4                                     # 14 rows / 4 per page
    assert len(seen) == 14 and len(set(seen)) == 14        # nothing skipped, nothing twice
    expected = [str(d["_id"]) for d in sorted(db.scan_history.docs, key=lambda d: (d["scanned_at"], d["_id"]), reverse=True)]
    assert seen == expected


def test_an_exactly_full_last_page_says_no_more(monkeypatch):
    app, db, _ = setup(monkeypatch)
    body = call(app, "GET", "/history/?limit=3").json()   # exactly 3 of mine
    assert len(body["items"]) == 3 and body["has_more"] is False and body["next_cursor"] is None


def test_bad_limit_and_bad_cursor_are_422(monkeypatch):
    app, _, _ = setup(monkeypatch)
    assert call(app, "GET", "/history/?limit=0").status_code == 422
    assert call(app, "GET", "/history/?limit=101").status_code == 422
    r = call(app, "GET", "/history/?cursor=garbage")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_cursor"


def test_a_cursor_never_reveals_another_users_rows(monkeypatch):
    app, db, entries = setup(monkeypatch)
    foreign = entries[3]                                  # newest of all, but OTHER's
    cursor = encode_cursor(foreign["scanned_at"] + timedelta(minutes=1), foreign["_id"])
    ids = [x["id"] for x in call(app, "GET", f"/history/?cursor={cursor}").json()["items"]]
    assert str(foreign["_id"]) not in ids and len(ids) == 3


def test_delete_one_removes_only_that_entry(monkeypatch):
    app, db, entries = setup(monkeypatch)
    target = entries[1]
    assert call(app, "DELETE", f"/history/{target['_id']}").status_code == 204
    assert target not in db.scan_history.docs and len(db.scan_history.docs) == 3


def test_cannot_delete_someone_elses_entry_and_unknown_ids_are_404(monkeypatch):
    app, db, entries = setup(monkeypatch)
    assert call(app, "DELETE", f"/history/{entries[3]['_id']}").status_code == 404   # belongs to OTHER
    assert call(app, "DELETE", f"/history/{ObjectId()}").status_code == 404
    assert call(app, "DELETE", "/history/not-an-object-id").status_code == 404
    assert len(db.scan_history.docs) == 4


def test_clear_deletes_only_my_entries(monkeypatch):
    app, db, entries = setup(monkeypatch)
    others = entries[3]                      # `entries` is the fake DB's own list, so grab it first
    assert call(app, "DELETE", "/history/").status_code == 204
    assert db.scan_history.docs == [others]


def test_count_is_mine_only_and_follows_deletes(monkeypatch):
    app, db, entries = setup(monkeypatch)
    assert call(app, "GET", "/history/count").json() == {"count": 3}   # OTHER's entry not counted
    call(app, "DELETE", f"/history/{entries[0]['_id']}")
    assert call(app, "GET", "/history/count").json() == {"count": 2}
    call(app, "DELETE", "/history/")
    assert call(app, "GET", "/history/count").json() == {"count": 0}
