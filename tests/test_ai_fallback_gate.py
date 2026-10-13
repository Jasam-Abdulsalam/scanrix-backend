import asyncio

from app.api.v1.endpoints import scan
from app.core.config import settings


def test_fallback_is_off_by_default():
    assert settings.AI_FALLBACK_ENABLED is False


def test_background_fallback_only_queues_unknowns_and_never_rewrites_product(monkeypatch):
    """Regression: the fallback used to overwrite the product's score/ingredients
    with an AI analysis of just the unknown ingredients."""
    seen = []

    async def fake_process(name, category):
        seen.append((name, category))

    monkeypatch.setattr(scan.ai_fallback_service, "process_unknown_ingredient", fake_process)

    asyncio.run(scan.run_ai_fallback_background(["xyzzy flavour", "foo gum"], "food"))

    assert seen == [("xyzzy flavour", "food"), ("foo gum", "food")]
    assert not hasattr(scan, "update_product_analysis")
    assert not hasattr(scan, "ai_service")
