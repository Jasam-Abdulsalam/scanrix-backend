import asyncio
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1.endpoints.history import router
from app.crud import crud_history, crud_product

ME, OTHER = ObjectId(), ObjectId()


class Result:
    def __init__(self, n):
        self.deleted_count = n


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction):
        self.docs = sorted(self.docs, key=lambda d: d[key], reverse=direction == -1)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, length=None):
        return list(self.docs)


class FakeHistory:
    def __init__(self, docs):
        self.docs = docs
        self.product_queries = 0

    def find(self, filt):
        return Cursor([d for d in self.docs if d["user_id"] == filt["user_id"]])

    async def delete_one(self, filt):
        hit = [d for d in self.docs if d["_id"] == filt["_id"] and d["user_id"] == filt["user_id"]]
        for d in hit:
            self.docs.remove(d)
        return Result(len(hit))

    async def delete_many(self, filt):
        hit = [d for d in self.docs if d["user_id"] == filt["user_id"]]
        for d in hit:
            self.docs.remove(d)
        return Result(len(hit))


class FakeProducts:
    def __init__(self, docs):
        self.docs = docs
        self.queries = 0

    def find(self, filt):
        self.queries += 1
        wanted = filt["_id"]["$in"]
        return Cursor([d for d in self.docs if d["_id"] in wanted])


class FakeDb:
    def __init__(self, history, products):
        self.scan_history = FakeHistory(history)
        self.products = FakeProducts(products)


def _entry(user, product_id, minute, verdict="safe"):
    return {"_id": ObjectId(), "user_id": user, "product_id": product_id, "verdict": verdict,
            "personalized_score": None, "scanned_at": datetime(2026, 10, 1, 12, minute, tzinfo=timezone.utc)}


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


def test_list_is_newest_first_with_product_summary_and_only_mine(monkeypatch):
    app, db, _ = setup(monkeypatch)
    r = call(app, "GET", "/history/")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3                                   # the other user's entry is not included
    assert [x["scanned_at"] for x in rows] == sorted((x["scanned_at"] for x in rows), reverse=True)
    assert rows[1]["product"] == {"barcode": "b-two", "name": "two", "brand": "Brand",
                                  "category": "food", "image_url": "http://img/two.png"}
    assert rows[0]["product"] is None                       # deleted product: row still returned
    assert db.products.queries == 1                         # batched, not one query per row


def test_limit_is_validated(monkeypatch):
    app, _, _ = setup(monkeypatch)
    assert call(app, "GET", "/history/?limit=0").status_code == 422
    assert call(app, "GET", "/history/?limit=101").status_code == 422
    assert len(call(app, "GET", "/history/?limit=1").json()) == 1


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
