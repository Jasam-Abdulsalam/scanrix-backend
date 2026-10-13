import asyncio

from app.services.ingredient_db_service import ingredient_db_service


def test_no_ingredient_text_returns_none(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("engine must not run without ingredient text")

    monkeypatch.setattr(ingredient_db_service, "analyze_ingredients_text", boom)
    assert asyncio.run(ingredient_db_service.evaluate_product_ingredients([])) is None
    assert asyncio.run(ingredient_db_service.evaluate_product_ingredients([{"name": ""}, "junk"])) is None


def test_ingredient_names_are_joined_and_evaluated(monkeypatch):
    seen = {}

    async def fake(text, category="food", db=None):
        seen["args"] = (text, category)
        return "EVAL", []

    monkeypatch.setattr(ingredient_db_service, "analyze_ingredients_text", fake)
    out = asyncio.run(
        ingredient_db_service.evaluate_product_ingredients([{"name": "sugar"}, {"name": "salt"}], "cosmetic")
    )
    assert out == "EVAL"
    assert seen["args"] == ("sugar, salt", "cosmetic")


def _evaluation(recognised, total, severity="none"):
    from app.services.rule_engine import EvaluationResult
    return EvaluationResult(
        ruleset_version="t", coverage=round(recognised / total, 2), recognised_count=recognised,
        total_count=total, overall_severity=severity, disclaimer="d",
    )


def test_overlay_replaces_stale_stored_verdict_with_fresh_one():
    # Regression: a product saved as caution/70 with 0% coverage kept showing a green score.
    stored = {"barcode": "1", "verdict": "caution", "overall_score": 70, "summary": "old"}
    shown = ingredient_db_service.overlay_legacy_fields(stored, _evaluation(1, 9))
    assert shown["verdict"] == "caution" and shown["overall_score"] == 55
    assert "1 of 9" in shown["summary"]
    assert shown["barcode"] == "1"
    assert stored["overall_score"] == 70  # input not mutated


def test_overlay_without_evaluation_keeps_stored_values():
    stored = {"verdict": "unknown", "overall_score": 50, "summary": "No ingredient text"}
    assert ingredient_db_service.overlay_legacy_fields(stored, None) == stored
