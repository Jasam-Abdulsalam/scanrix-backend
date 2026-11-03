import asyncio
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.schemas.ai_alternatives import AIAlternativesRequest, AIAlternativesResult
from app.services import ai_alternatives_service as svc
from app.services import credits_service
from app.services.ai_alternatives_rules import build_prompt, clean_result, flagged_ingredients, parse_alternatives
from app.services.rule_engine import EvaluationResult, IngredientFinding

RESET = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
PRODUCT = {"barcode": "8901", "name": "Oil Control Face Wash", "brand": "Acme", "quantity": "100 ml",
           "category": "cosmetic", "ingredients": [{"name": "aqua"}, {"name": "linalool"}, {"name": "glycerin"}]}


def evaluation(flagged=("linalool",)):
    findings = [IngredientFinding(raw_name=n, canonical_name=n, matched=True, severity="medium", flags=["allergen"])
                for n in flagged]
    findings.append(IngredientFinding(raw_name="glycerin", canonical_name="glycerin", matched=True, severity="none"))
    return EvaluationResult(ruleset_version="t", coverage=1.0, recognised_count=len(findings),
                            total_count=len(findings), overall_severity="medium", findings=findings, disclaimer="d")


def ai_json(alternatives=None, product_type="foaming face wash"):
    alts = alternatives if alternatives is not None else [
        {"name": "Gentle Wash", "brand": "Good Co", "size": "100 ml", "price_inr": 299,
         "why_better": "No fragrance allergens.", "avoids": ["Linalool", "Parabens"]}]
    return json.dumps({"product_type": product_type, "original_price_inr": 250, "alternatives": alts})


class World:
    """Fakes for product lookup, cache, credits, engine and AI. Records what happened."""
    def __init__(self, monkeypatch, product=PRODUCT, cache=None, ai_text=None, credits=True, image=None):
        self.events, self.saved = [], {}

        async def find_image(name, brand, size=None, cosmetic=True):
            return image

        async def get_product(barcode):
            return product

        async def get_cached(key):
            return cache

        async def save(key, result, barcode, model):
            self.saved[key] = result

        async def reserve(user_id, action):
            if not credits:
                raise credits_service.CreditsExhausted(RESET)
            self.events.append(f"reserve:{action}")
            return credits_service.Reservation(user_id, action, "2026-W45")

        async def refund(reservation):
            self.events.append("refund")

        async def balance(user_id, now=None):
            return credits_service.CreditBalance(6, 4, RESET)

        async def analyze(text, category="food", db=None):
            return evaluation(), []

        async def generate(prompt):
            self.events.append("ai")
            self.prompt = prompt
            return ai_text, "groq"

        monkeypatch.setattr(svc, "get_product_by_barcode", get_product)
        monkeypatch.setattr(svc.crud_ai_alternatives, "get_cached", get_cached)
        monkeypatch.setattr(svc.crud_ai_alternatives, "save_alternatives", save)
        monkeypatch.setattr(svc.credits_service, "reserve_credit", reserve)
        monkeypatch.setattr(svc.credits_service, "refund_credit", refund)
        monkeypatch.setattr(svc.credits_service, "get_balance", balance)
        monkeypatch.setattr(svc.ingredient_db_service, "analyze_ingredients_text", analyze)
        monkeypatch.setattr(svc, "_generate", generate)
        monkeypatch.setattr(svc.product_image_service, "find_image", find_image)


def run(coro):
    return asyncio.run(coro)


# --- service: money and caching rules (same as 'Get AI verdict') ---

def test_new_product_costs_one_credit_calls_ai_and_saves(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json())
    out = run(svc.get_alternatives("u1", "8901"))
    assert w.events == ["reserve:ai_alternatives", "ai"] and len(w.saved) == 1
    assert out.cached is False and out.verified is False and out.source == "ai" and out.credits_remaining == 4
    assert out.product_type == "foaming face wash" and out.alternatives[0].price_inr == 299
    assert "not verified" in out.disclaimer.lower()


def test_saved_answer_is_free_and_makes_no_ai_call(monkeypatch):
    stored = {"result": json.loads(ai_json()), "created_at": RESET}
    w = World(monkeypatch, cache=stored)
    out = run(svc.get_alternatives("u1", "8901"))
    assert w.events == [] and w.saved == {} and out.cached is True and out.generated_at == RESET


def test_unusable_ai_answer_refunds_and_saves_nothing(monkeypatch):
    too_many = [{"name": f"P{i}", "brand": "B", "why_better": "x"} for i in range(4)]
    for text in (None, "not json", json.dumps({"alternatives": []}), ai_json(alternatives=too_many)):
        w = World(monkeypatch, ai_text=text)
        with pytest.raises(svc.AIUnavailableError):
            run(svc.get_alternatives("u1", "8901"))
        assert w.events == ["reserve:ai_alternatives", "ai", "refund"] and w.saved == {}


def test_no_confident_alternative_is_a_saved_answer_not_an_error(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json(alternatives=[]))
    out = run(svc.get_alternatives("u1", "8901"))
    assert out.alternatives == [] and len(w.saved) == 1 and "refund" not in w.events


def test_no_credits_means_no_ai_call(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json(), credits=False)
    with pytest.raises(credits_service.CreditsExhausted):
        run(svc.get_alternatives("u1", "8901"))
    assert w.events == []


def test_missing_product_and_missing_ingredients(monkeypatch):
    World(monkeypatch, product=None)
    with pytest.raises(svc.ProductNotFoundError):
        run(svc.get_alternatives("u1", "8901"))
    World(monkeypatch, product={**PRODUCT, "ingredients": []})
    with pytest.raises(svc.IngredientsMissingError):
        run(svc.get_alternatives("u1", "8901"))


def test_prompt_names_the_product_and_its_flagged_ingredients(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json())
    run(svc.get_alternatives("u1", "8901"))
    assert "Oil Control Face Wash" in w.prompt and "100 ml" in w.prompt and '"linalool"' in w.prompt
    assert "same product type" in w.prompt and "India" in w.prompt


# --- pure rules ---

def test_avoids_keeps_only_real_flagged_ingredients():
    result = AIAlternativesResult(**json.loads(ai_json()))
    flagged = flagged_ingredients(evaluation())
    cleaned = clean_result(result, ["aqua", "linalool", "glycerin"], flagged)
    assert cleaned.alternatives[0].avoids == ["Linalool"]  # "Parabens" was never in the product


def test_flagged_ingredients_skip_clean_and_unmatched_ones():
    assert [f["name"] for f in flagged_ingredients(evaluation())] == ["linalool"]


def test_parse_rejects_bad_shapes_and_accepts_fenced_json():
    assert parse_alternatives(None) is None and parse_alternatives("nope") is None
    assert parse_alternatives(json.dumps({"product_type": "x", "alternatives": [{"name": "a"}]})) is None
    assert parse_alternatives("```json\n" + ai_json() + "\n```").alternatives[0].brand == "Good Co"


def test_build_prompt_handles_unknown_fields():
    prompt = build_prompt({"category": "food"}, ["sugar"], [])
    assert '"unknown"' in prompt and "sugar" in prompt


# --- endpoint: errors map to the same codes as 'Get AI verdict' ---

@pytest.fixture
def client():
    app.dependency_overrides[deps.get_current_user] = lambda: {"_id": "u1"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_maps_errors(client, monkeypatch):
    async def exhausted(user_id, barcode):
        raise credits_service.CreditsExhausted(RESET)

    monkeypatch.setattr(svc, "get_alternatives", exhausted)
    r = client.post("/api/v1/ai/alternatives", json={"barcode": "8901"})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "ai_credits_exhausted" and "Retry-After" in r.headers

    async def unavailable(user_id, barcode):
        raise svc.AIUnavailableError("x")

    monkeypatch.setattr(svc, "get_alternatives", unavailable)
    r = client.post("/api/v1/ai/alternatives", json={"barcode": "8901"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"


def test_endpoint_rejects_a_bad_barcode(client):
    assert client.post("/api/v1/ai/alternatives", json={"barcode": "x"}).status_code == 422
    assert AIAlternativesRequest(barcode="8901138512187").barcode


# --- product photos ---

def test_photos_are_added_by_the_backend_and_saved_with_the_answer(monkeypatch):
    w = World(monkeypatch, ai_text=ai_json(), image="https://img.example/wash.jpg")
    out = run(svc.get_alternatives("u1", "8901"))
    assert out.alternatives[0].image_url == "https://img.example/wash.jpg"
    assert list(w.saved.values())[0]["alternatives"][0]["image_url"] == "https://img.example/wash.jpg"


def test_an_ai_written_image_link_is_never_kept(monkeypatch):
    alt = {"name": "Gentle Wash", "brand": "Good Co", "why_better": "x", "image_url": "https://made.up/x.jpg"}
    World(monkeypatch, ai_text=ai_json(alternatives=[alt]), image=None)
    assert run(svc.get_alternatives("u1", "8901")).alternatives[0].image_url is None


def test_slow_image_lookups_are_dropped_not_fatal(monkeypatch):
    World(monkeypatch, ai_text=ai_json())

    async def slow(name, brand, size=None, cosmetic=True):
        await asyncio.sleep(1)
        return "https://img.example/late.jpg"

    monkeypatch.setattr(svc.product_image_service, "find_image", slow)
    monkeypatch.setattr(svc.settings, "PRODUCT_IMAGES_TOTAL_SECONDS", 0.05)
    out = run(svc.get_alternatives("u1", "8901"))
    assert out.alternatives and out.alternatives[0].image_url is None
