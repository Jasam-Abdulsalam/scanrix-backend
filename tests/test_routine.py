import asyncio
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1.endpoints.routine import router
from app.crud import crud_product, crud_routine
from app.crud.crud_routine import AddResult
from app.services import routine_service
from tests.fake_mongo import FakeCollection

ME = ObjectId()


class FakeRoutines:
    """In-memory stand-in for crud_routine with the same rules (no duplicates, per-slot cap, guarded reorder).
    The real atomic Mongo filters are covered by the crud docstrings; tests/fake_mongo has no $push/$pull."""

    def __init__(self):
        self.docs = {}

    async def get_routine(self, user_id):
        return self.docs.get(user_id)

    async def add_item(self, user_id, slot, product_id, barcode, max_items):
        doc = self.docs.setdefault(user_id, {"morning": [], "evening": []})
        if any(i["barcode"] == barcode for i in doc[slot]):
            return AddResult.ALREADY_THERE
        if len(doc[slot]) >= max_items:
            return AddResult.FULL
        doc[slot].append({"product_id": product_id, "barcode": barcode, "added_at": datetime.now(timezone.utc)})
        return AddResult.ADDED

    async def remove_item(self, user_id, slot, barcode):
        doc = self.docs.get(user_id)
        if doc:
            doc[slot] = [i for i in doc[slot] if i["barcode"] != barcode]
            if not any(i["barcode"] == barcode for s in ("morning", "evening") for i in doc[s]):
                doc.get("product_types", {}).pop(barcode, None)

    async def set_product_type(self, user_id, barcode, product_type):
        doc = self.docs.get(user_id)
        if not doc or not any(i["barcode"] == barcode for s in ("morning", "evening") for i in doc[s]):
            return False
        types = doc.setdefault("product_types", {})
        if product_type:
            types[barcode] = product_type
        else:
            types.pop(barcode, None)
        return True

    async def set_order(self, user_id, slot, items):
        doc = self.docs.get(user_id) or {}
        if sorted(i["barcode"] for i in doc.get(slot, [])) != sorted(i["barcode"] for i in items):
            return False
        doc[slot] = items
        return True


def _product(n, category="cosmetic"):
    return {"_id": ObjectId(), "barcode": f"bc{n:04d}", "name": f"Product {n}", "brand": "Brand",
            "category": category, "image_url": None, "verdict": "caution", "overall_score": 60}


def setup(monkeypatch, cap=15):
    products = [_product(i) for i in range(4)] + [_product(9, category="food")]

    class Db:
        pass

    db = Db()
    db.products = FakeCollection(products)
    monkeypatch.setattr(crud_product, "get_database", lambda: db)
    fake = FakeRoutines()
    for name in ("get_routine", "add_item", "remove_item", "set_order", "set_product_type"):
        monkeypatch.setattr(crud_routine, name, getattr(fake, name))
    monkeypatch.setattr(routine_service.settings, "ROUTINE_MAX_PER_SLOT", cap)
    app = FastAPI()
    app.include_router(router, prefix="/routine")
    app.dependency_overrides[get_current_user] = lambda: {"_id": ME}
    return app, fake, products


def call(app, method, path, json=None):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.request(method, path, json=json)
    return asyncio.run(go())


def barcodes(app, slot):
    return [i["barcode"] for i in call(app, "GET", "/routine/").json()[slot]]


def test_add_is_idempotent_per_slot_and_listed_with_product_fields(monkeypatch):
    app, _, _ = setup(monkeypatch)
    assert call(app, "PUT", "/routine/morning/bc0000").status_code == 204
    assert call(app, "PUT", "/routine/morning/bc0000").status_code == 204  # repeat: still one step
    assert call(app, "PUT", "/routine/evening/bc0000").status_code == 204  # same product, other slot: fine
    body = call(app, "GET", "/routine/").json()
    assert [i["barcode"] for i in body["morning"]] == ["bc0000"] and [i["barcode"] for i in body["evening"]] == ["bc0000"]
    assert body["morning"][0]["name"] == "Product 0" and body["morning"][0]["verdict"] == "caution"


def test_empty_routine(monkeypatch):
    app, _, _ = setup(monkeypatch)
    assert call(app, "GET", "/routine/").json() == {"morning": [], "evening": []}


def test_add_errors(monkeypatch):
    app, _, _ = setup(monkeypatch, cap=2)
    assert call(app, "PUT", "/routine/morning/nope0000").status_code == 404
    r = call(app, "PUT", "/routine/morning/bc0009")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "not_cosmetic"
    call(app, "PUT", "/routine/morning/bc0000")
    call(app, "PUT", "/routine/morning/bc0001")
    r = call(app, "PUT", "/routine/morning/bc0002")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "routine_slot_full"
    assert call(app, "PUT", "/routine/morning/bc0001").status_code == 204  # already there: not "full"


def test_remove_is_idempotent(monkeypatch):
    app, _, _ = setup(monkeypatch)
    call(app, "PUT", "/routine/evening/bc0000")
    assert call(app, "DELETE", "/routine/evening/bc0000").status_code == 204
    assert call(app, "DELETE", "/routine/evening/bc0000").status_code == 204
    assert barcodes(app, "evening") == []


def test_reorder(monkeypatch):
    app, _, _ = setup(monkeypatch)
    for bc in ("bc0000", "bc0001", "bc0002"):
        call(app, "PUT", f"/routine/morning/{bc}")
    assert call(app, "PUT", "/routine/morning", json={"barcodes": ["bc0002", "bc0000", "bc0001"]}).status_code == 204
    assert barcodes(app, "morning") == ["bc0002", "bc0000", "bc0001"]


def test_reorder_must_hold_exactly_the_current_products(monkeypatch):
    app, _, _ = setup(monkeypatch)
    for bc in ("bc0000", "bc0001"):
        call(app, "PUT", f"/routine/morning/{bc}")
    for wrong in (["bc0000"], ["bc0000", "bc0001", "bc0002"], ["bc0000", "bc0000"], ["bc0000", "bc0003"]):
        r = call(app, "PUT", "/routine/morning", json={"barcodes": wrong})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "order_mismatch", wrong
    assert barcodes(app, "morning") == ["bc0000", "bc0001"]


def test_concurrent_change_during_reorder_is_a_mismatch(monkeypatch):
    app, fake, _ = setup(monkeypatch)
    for bc in ("bc0000", "bc0001"):
        call(app, "PUT", f"/routine/morning/{bc}")

    async def changed(user_id, slot, items):
        return False  # the guarded write found a different slot

    monkeypatch.setattr(crud_routine, "set_order", changed)
    r = call(app, "PUT", "/routine/morning", json={"barcodes": ["bc0001", "bc0000"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "order_mismatch"


def test_deleted_product_is_left_out(monkeypatch):
    app, _, products = setup(monkeypatch)
    call(app, "PUT", "/routine/morning/bc0000")
    call(app, "PUT", "/routine/morning/bc0001")
    crud_product.get_database().products.docs.remove(products[0])
    assert barcodes(app, "morning") == ["bc0001"]


def test_validation(monkeypatch):
    app, _, _ = setup(monkeypatch)
    assert call(app, "PUT", "/routine/noon/bc0000").status_code == 422  # unknown slot
    assert call(app, "PUT", "/routine/morning/x").status_code == 422  # barcode too short
    assert call(app, "PUT", "/routine/morning", json={}).status_code == 422


def test_requires_auth(monkeypatch):
    app, _, _ = setup(monkeypatch)
    app.dependency_overrides.clear()
    assert call(app, "GET", "/routine/").status_code in (401, 403)


def _types(app):
    body = call(app, "GET", "/routine/").json()
    return {slot: {i["barcode"]: i["product_type"] for i in body[slot]} for slot in ("morning", "evening")}


def test_product_type_is_shared_by_both_slots_and_clearable(monkeypatch):
    app, _, _ = setup(monkeypatch)
    call(app, "PUT", "/routine/morning/bc0000")
    call(app, "PUT", "/routine/evening/bc0000")
    call(app, "PUT", "/routine/morning/bc0001")
    assert call(app, "PUT", "/routine/product-type/bc0000", json={"product_type": "serum"}).status_code == 204
    assert _types(app) == {"morning": {"bc0000": "serum", "bc0001": None}, "evening": {"bc0000": "serum"}}
    assert call(app, "PUT", "/routine/product-type/bc0000", json={"product_type": None}).status_code == 204
    assert _types(app)["morning"]["bc0000"] is None


def test_product_type_needs_the_product_in_a_slot_and_a_known_value(monkeypatch):
    app, _, _ = setup(monkeypatch)
    r = call(app, "PUT", "/routine/product-type/bc0000", json={"product_type": "serum"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_in_routine"
    call(app, "PUT", "/routine/morning/bc0000")
    assert call(app, "PUT", "/routine/product-type/bc0000", json={"product_type": "shampoo"}).status_code == 422


def test_product_type_is_dropped_once_the_product_leaves_both_slots(monkeypatch):
    app, fake, _ = setup(monkeypatch)
    call(app, "PUT", "/routine/morning/bc0000")
    call(app, "PUT", "/routine/evening/bc0000")
    call(app, "PUT", "/routine/product-type/bc0000", json={"product_type": "toner"})
    call(app, "DELETE", "/routine/morning/bc0000")
    assert _types(app)["evening"]["bc0000"] == "toner"  # still in the evening: kept
    call(app, "DELETE", "/routine/evening/bc0000")
    call(app, "PUT", "/routine/morning/bc0000")
    assert _types(app)["morning"]["bc0000"] is None  # re-added later: starts unlabelled
