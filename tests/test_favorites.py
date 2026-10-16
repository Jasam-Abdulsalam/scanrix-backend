import asyncio
from datetime import datetime, timedelta

import httpx
from bson import ObjectId
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1.endpoints.favorites import router
from app.crud import crud_favorites, crud_product
from app.services import favorites_service
from tests.fake_mongo import FakeCollection

ME, OTHER = ObjectId(), ObjectId()
T0 = datetime(2026, 10, 1, 12, 0)


class FakeDb:
    def __init__(self, products):
        self.products = FakeCollection(products)
        self.favorites = FakeCollection()


def _product(n):
    return {"_id": ObjectId(), "barcode": f"b{n}", "name": f"Product {n}", "brand": "Brand", "category": "food",
            "image_url": None, "verdict": "safe", "overall_score": 80}


def setup(monkeypatch, count=3, cap=500):
    products = [_product(i) for i in range(count)]
    db = FakeDb(products)
    for mod in (crud_favorites, crud_product):
        monkeypatch.setattr(mod, "get_database", lambda: db)
    monkeypatch.setattr(favorites_service.settings, "FAVORITES_MAX_PER_USER", cap)
    app = FastAPI()
    app.include_router(router, prefix="/favorites")
    app.dependency_overrides[get_current_user] = lambda: {"_id": ME}
    return app, db, products


def call(app, method, path):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.request(method, path)
    return asyncio.run(go())


def test_add_is_idempotent_and_listed_with_product_fields(monkeypatch):
    app, db, products = setup(monkeypatch)
    assert call(app, "PUT", "/favorites/b0").status_code == 204
    assert call(app, "PUT", "/favorites/b0").status_code == 204            # repeat: still one row
    assert len(db.favorites.docs) == 1
    body = call(app, "GET", "/favorites/").json()
    assert [i["barcode"] for i in body["items"]] == ["b0"]
    assert body["items"][0]["name"] == "Product 0" and body["items"][0]["verdict"] == "safe"
    assert body["has_more"] is False


def test_unknown_barcode_is_404(monkeypatch):
    app, db, _ = setup(monkeypatch)
    assert call(app, "PUT", "/favorites/nope").status_code == 404
    assert db.favorites.docs == []


def test_remove_is_idempotent(monkeypatch):
    app, db, _ = setup(monkeypatch)
    call(app, "PUT", "/favorites/b0")
    assert call(app, "DELETE", "/favorites/b0").status_code == 204
    assert call(app, "DELETE", "/favorites/b0").status_code == 204        # not saved any more: still 204
    assert db.favorites.docs == []


def test_cap_blocks_new_ones_with_409_but_not_a_repeat_of_a_saved_one(monkeypatch):
    app, db, _ = setup(monkeypatch, count=3, cap=2)
    assert call(app, "PUT", "/favorites/b0").status_code == 204
    assert call(app, "PUT", "/favorites/b1").status_code == 204
    r = call(app, "PUT", "/favorites/b2")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "favorites_limit_reached"
    assert call(app, "PUT", "/favorites/b0").status_code == 204            # already saved: allowed at the cap
    assert len(db.favorites.docs) == 2


def test_barcodes_endpoint_lists_only_mine(monkeypatch):
    app, db, products = setup(monkeypatch)
    call(app, "PUT", "/favorites/b0")
    call(app, "PUT", "/favorites/b2")
    db.favorites.docs.append({"_id": ObjectId(), "user_id": OTHER, "product_id": products[1]["_id"],
                              "barcode": "b1", "created_at": T0})
    assert sorted(call(app, "GET", "/favorites/barcodes").json()["barcodes"]) == ["b0", "b2"]


def test_list_is_newest_saved_first_paginated_and_skips_deleted_products(monkeypatch):
    app, db, products = setup(monkeypatch, count=5)
    for i, p in enumerate(products):
        db.favorites.docs.append({"_id": ObjectId(), "user_id": ME, "product_id": p["_id"], "barcode": p["barcode"],
                                  "created_at": T0 + timedelta(minutes=i)})
    db.favorites.docs.append({"_id": ObjectId(), "user_id": OTHER, "product_id": products[0]["_id"],
                              "barcode": "b0", "created_at": T0 + timedelta(minutes=99)})
    db.products.docs.remove(products[3])                                    # b3 no longer exists
    seen, cursor = [], None
    while True:
        body = call(app, "GET", "/favorites/?limit=2" + (f"&cursor={cursor}" if cursor else "")).json()
        seen += [i["barcode"] for i in body["items"]]
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
    assert seen == ["b4", "b2", "b1", "b0"]                                 # newest first, b3 left out, nothing of OTHER's


def test_bad_limit_and_cursor_are_422(monkeypatch):
    app, _, _ = setup(monkeypatch)
    assert call(app, "GET", "/favorites/?limit=0").status_code == 422
    assert call(app, "GET", "/favorites/?limit=101").status_code == 422
    r = call(app, "GET", "/favorites/?cursor=garbage")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_cursor"


def test_deleting_an_account_removes_only_that_users_favorites(monkeypatch):
    app, db, products = setup(monkeypatch)
    call(app, "PUT", "/favorites/b0")
    other = {"_id": ObjectId(), "user_id": OTHER, "product_id": products[0]["_id"], "barcode": "b0", "created_at": T0}
    db.favorites.docs.append(other)
    assert asyncio.run(crud_favorites.delete_user_favorites(str(ME))) == 1
    assert db.favorites.docs == [other]
