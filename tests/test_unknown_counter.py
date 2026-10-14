import asyncio

from app.crud import crud_unknown_ingredient as crud
from app.services.ingredient_db_service import ingredient_db_service


class FakeCollection:
    def __init__(self):
        self.ops = None

    async def bulk_write(self, ops, ordered=True):
        self.ops = ops


class FakeDb:
    def __init__(self):
        self.unknown_ingredients = FakeCollection()


def test_clean_names_lowercases_dedupes_and_drops_noise():
    out = crud.clean_unknown_names(["Glycerin", " glycerin ", "", "x" * 200, None, "Stearic Acid"])
    assert out == ["glycerin", "stearic acid"]


def test_clean_names_is_capped():
    out = crud.clean_unknown_names([f"n{i}" for i in range(500)])
    assert len(out) == crud.MAX_NAMES_PER_SCAN


def test_record_sends_one_atomic_upsert_per_name(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(crud, "get_database", lambda: db)
    n = asyncio.run(crud.record_unknown_ingredients(["Glycerin", "neem"], "cosmetic", "123"))
    assert n == 2 and len(db.unknown_ingredients.ops) == 2
    op = db.unknown_ingredients.ops[0]._doc
    assert op["$inc"] == {"scan_count": 1}
    assert op["$setOnInsert"]["example_barcode"] == "123"
    assert db.unknown_ingredients.ops[0]._upsert is True


def test_record_ignores_empty_and_invalid_category(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(crud, "get_database", lambda: db)
    assert asyncio.run(crud.record_unknown_ingredients([], "food")) == 0
    assert asyncio.run(crud.record_unknown_ingredients(["x1"], "<script>")) == 0
    assert db.unknown_ingredients.ops is None


def test_service_swallows_counter_failures(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("mongo down")

    monkeypatch.setattr("app.services.ingredient_db_service.record_unknown_ingredients", boom)
    asyncio.run(ingredient_db_service.record_unknowns(["x"], "food"))  # must not raise


def test_stored_product_without_text_reports_no_unknowns():
    out = asyncio.run(ingredient_db_service.evaluate_stored_product([]))
    assert out == (None, [])
