import asyncio
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.schemas.ai_natural_remedy import AINaturalRemedyResult, NaturalRemedyRequest
from app.services import ai_natural_remedy_service as svc
from app.services import credits_service
from app.services.ai_natural_remedy_rules import (
    ALL_REMOVED_REASON, NO_REMEDY_REASON, build_prompt, clean_result, parse_result,
)

RESET = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
PRODUCT = {"barcode": "8901", "name": "Oil Control Face Wash", "brand": "Acme", "category": "cosmetic",
           "ingredients": [{"name": "aqua"}, {"name": "sodium laureth sulfate"}, {"name": "fragrance"}]}
LABEL = NaturalRemedyRequest(ingredients_text="Aqua, Sodium Laureth Sulfate, Parfum", category="cosmetic")


def remedy(name="Besan and rose water cleanser", items=("besan", "rose water"), steps=("Mix to a paste.",)):
    return {"name": name, "replaces": "face wash", "ingredients": [{"item": i, "amount": "2 tsp"} for i in items],
            "steps": list(steps), "how_often": "Once a day", "keeps_for": "Make fresh each time",
            "why": "Cleans gently without sulfates.", "caution": None}


def ai_json(remedies=None, product_type="foaming face wash", reason=None):
    rs = remedies if remedies is not None else [remedy()]
    return json.dumps({"product_type": product_type, "remedies": rs, "no_remedy_reason": reason})


class World:
    """Fakes for product lookup, cache, credits and AI. Records what happened."""
    def __init__(self, monkeypatch, product=PRODUCT, cache=None, ai_text=None, credits=True):
        self.events, self.saved = [], {}

        async def get_product(barcode):
            return product

        async def get_cached(key):
            return cache

        async def save(key, result, barcode, model):
            self.saved[key] = (result, barcode)

        async def reserve(user_id, action):
            if not credits:
                raise credits_service.CreditsExhausted(RESET)
            self.events.append(f"reserve:{action}")
            return credits_service.Reservation(user_id, action, "2026-W45")

        async def refund(reservation):
            self.events.append("refund")

        async def balance(user_id, now=None):
            return credits_service.CreditBalance(6, 4, RESET)

        async def generate(prompt):
            self.events.append("ai")
            self.prompt = prompt
            return ai_text, "groq"

        monkeypatch.setattr("app.services.ai_product_service.get_product_by_barcode", get_product)
        monkeypatch.setattr(svc.crud_ai_natural_remedy, "get_cached", get_cached)
        monkeypatch.setattr(svc.crud_ai_natural_remedy, "save_remedy", save)
        monkeypatch.setattr(svc.credits_service, "reserve_credit", reserve)
        monkeypatch.setattr(svc.credits_service, "refund_credit", refund)
        monkeypatch.setattr(svc.credits_service, "get_balance", balance)
        monkeypatch.setattr(svc, "_generate", generate)


def run(coro):
    return asyncio.run(coro)


BARCODE = NaturalRemedyRequest(barcode="8901")


# --- service: money and caching rules (same as 'Get AI verdict') ---

def test_new_product_costs_one_credit_calls_ai_and_saves(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json())
    out = run(svc.get_remedy("u1", BARCODE))
    assert w.events == ["reserve:ai_natural_remedy", "ai"] and len(w.saved) == 1
    assert out.cached is False and out.verified is False and out.credits_remaining == 4
    assert out.remedies[0].ingredients[0].item == "besan" and out.no_remedy_reason is None
    assert "patch test" in out.patch_test_note.lower() and "not verified" in out.disclaimer.lower()


def test_saved_answer_is_free_and_makes_no_ai_call(monkeypatch):
    w = World(monkeypatch, cache={"result": json.loads(ai_json()), "created_at": RESET})
    out = run(svc.get_remedy("u1", BARCODE))
    assert w.events == [] and w.saved == {} and out.cached is True and out.generated_at == RESET


def test_unusable_ai_answer_refunds_and_saves_nothing(monkeypatch):
    too_many = [remedy(), remedy(), remedy()]
    too_many_steps = [remedy(steps=["a", "b", "c", "d", "e"])]
    for text in (None, "not json", json.dumps({"remedies": []}), ai_json(too_many), ai_json(too_many_steps)):
        w = World(monkeypatch, ai_text=text)
        with pytest.raises(svc.AIUnavailableError):
            run(svc.get_remedy("u1", BARCODE))
        assert w.events == ["reserve:ai_natural_remedy", "ai", "refund"] and w.saved == {}


def test_no_credits_means_no_ai_call(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json(), credits=False)
    with pytest.raises(credits_service.CreditsExhausted):
        run(svc.get_remedy("u1", BARCODE))
    assert w.events == []


def test_only_cosmetics_and_never_charged_for_others(monkeypatch):
    w = World(monkeypatch, product={**PRODUCT, "category": "food"}, ai_text=ai_json())
    with pytest.raises(svc.NotCosmeticError):
        run(svc.get_remedy("u1", BARCODE))
    with pytest.raises(svc.NotCosmeticError):
        run(svc.get_remedy("u1", NaturalRemedyRequest(ingredients_text="Sugar, Salt", category="food")))
    assert w.events == []


def test_missing_product_and_missing_ingredients(monkeypatch):
    World(monkeypatch, product=None)
    with pytest.raises(svc.ProductNotFoundError):
        run(svc.get_remedy("u1", BARCODE))
    World(monkeypatch, product={**PRODUCT, "ingredients": []})
    with pytest.raises(svc.IngredientsMissingError):
        run(svc.get_remedy("u1", BARCODE))


def test_label_scan_works_without_a_barcode(monkeypatch):
    w = World(monkeypatch, product=None, ai_text=ai_json())
    out = run(svc.get_remedy("u1", LABEL))
    assert out.remedies and list(w.saved.values())[0][1] is None  # saved with no barcode
    assert '"unknown"' in w.prompt and "sodium laureth sulfate" in w.prompt.lower()


def test_prompt_names_the_product_and_the_rules(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json())
    run(svc.get_remedy("u1", BARCODE))
    assert "Oil Control Face Wash" in w.prompt and "kitchen" in w.prompt and "NEVER use lemon" in w.prompt


def test_unsafe_product_type_is_a_saved_answer_with_no_remedies(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json(product_type="sunscreen lotion"))
    out = run(svc.get_remedy("u1", BARCODE))
    assert out.remedies == [] and out.no_remedy_reason == NO_REMEDY_REASON
    assert len(w.saved) == 1 and "refund" not in w.events


# --- pure safety rules ---

def result(remedies, product_type="foaming face wash", reason=None):
    return AINaturalRemedyResult(**json.loads(ai_json(remedies, product_type, reason)))


def test_remedies_with_blocked_ingredients_are_dropped_wherever_they_appear():
    ok = remedy()
    lemon = remedy(name="Honey lemon wash", items=("honey",))
    soda = remedy(items=("Baking Soda", "water"))
    in_steps = remedy(steps=["Mix besan and curd.", "Add 2 drops of tea tree essential oil."])
    cleaned = clean_result(result([ok, lemon]), None)
    assert [r.name for r in cleaned.remedies] == [ok["name"]] and cleaned.no_remedy_reason is None
    cleaned = clean_result(result([soda, in_steps]), None)
    assert cleaned.remedies == [] and cleaned.no_remedy_reason == ALL_REMOVED_REASON


def test_blocklist_matches_whole_words_only():
    sublime = remedy(name="Sublime oat scrub", items=("oats", "eggplant-free curd"))
    assert clean_result(result([sublime]), None).remedies  # "sublime" isn't lime, "eggplant" isn't egg


def test_no_remedy_types_checked_on_type_and_product_name():
    assert clean_result(result([remedy()], product_type="hair dye"), None).remedies == []
    named = clean_result(result([remedy()], product_type="cream"), "Daily Moisturiser SPF 30")
    assert named.remedies == [] and named.no_remedy_reason == NO_REMEDY_REASON
    assert clean_result(result([remedy()], product_type="hair oil"), "Coconut Hair Oil").remedies


def test_ai_own_no_remedy_reason_is_kept_when_it_gave_none():
    cleaned = clean_result(result([], reason="Nothing homemade cleans like this."), None)
    assert cleaned.no_remedy_reason == "Nothing homemade cleans like this."
    assert clean_result(result([]), None).no_remedy_reason == ALL_REMOVED_REASON


def test_parse_rejects_bad_shapes_and_accepts_fenced_json():
    assert parse_result(None) is None and parse_result("nope") is None
    assert parse_result(json.dumps({"product_type": "x", "remedies": [{"name": "a"}]})) is None
    assert parse_result("```json\n" + ai_json() + "\n```").remedies[0].replaces == "face wash"


def test_build_prompt_handles_no_product():
    prompt = build_prompt(None, ["aqua"])
    assert '"unknown"' in prompt and "aqua" in prompt


# --- endpoint ---

@pytest.fixture
def client():
    app.dependency_overrides[deps.get_current_user] = lambda: {"_id": "u1"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_maps_errors(client, monkeypatch):
    cases = [
        (credits_service.CreditsExhausted(RESET), 429, "ai_credits_exhausted"),
        (svc.AIUnavailableError("x"), 503, "ai_unavailable"),
        (svc.NotCosmeticError(), 422, "not_cosmetic"),
        (svc.IngredientsMissingError(), 422, "ingredients_missing"),
    ]
    for error, code, name in cases:
        async def fail(user_id, request, error=error):
            raise error

        monkeypatch.setattr(svc, "get_remedy", fail)
        r = client.post("/api/v1/ai/natural-remedy", json={"barcode": "8901"})
        assert r.status_code == code and r.json()["detail"]["code"] == name


def test_endpoint_validates_the_source(client):
    assert client.post("/api/v1/ai/natural-remedy", json={}).status_code == 422
    both = {"barcode": "8901", "ingredients_text": "Aqua, Glycerin", "category": "cosmetic"}
    assert client.post("/api/v1/ai/natural-remedy", json=both).status_code == 422
