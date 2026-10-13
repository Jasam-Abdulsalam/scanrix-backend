from app.services.ingredient_db_service import ingredient_db_service
from app.services.rule_engine import EvaluationResult


def _eval(severity="none", recognised=0, total=10):
    return EvaluationResult(
        ruleset_version="t",
        coverage=round(recognised / total, 2) if total else 0.0,
        recognised_count=recognised,
        total_count=total,
        overall_severity=severity,
        disclaimer="d",
    )


def _legacy(**kw):
    return ingredient_db_service.calculate_legacy_verdict_and_score(_eval(**kw))


def test_nothing_recognised_is_unknown_not_safe():
    # Regression: 0% coverage used to return caution/70, which the app painted green "GOOD".
    verdict, score, summary = _legacy(recognised=0, total=23)
    assert verdict == "unknown"
    assert score == 50
    assert "none of the 23" in summary


def test_low_coverage_never_scores_as_good():
    verdict, score, summary = _legacy(recognised=3, total=10)
    assert verdict == "caution"
    assert score < 70
    assert "3 of 10" in summary


def test_high_coverage_without_hazards_is_safe():
    assert _legacy(recognised=8, total=10)[:2] == ("safe", 90)
    assert _legacy(severity="low", recognised=8, total=10)[:2] == ("safe", 80)


def test_flagged_hazard_wins_even_at_zero_coverage():
    assert _legacy(severity="critical", recognised=0, total=5)[:2] == ("avoid", 15)
    assert _legacy(severity="high", recognised=1, total=20)[:2] == ("avoid", 35)
    assert _legacy(severity="medium", recognised=0, total=5)[:2] == ("caution", 60)


def test_no_ingredients_read_is_unknown():
    verdict, score, summary = _legacy(recognised=0, total=0)
    assert (verdict, score) == ("unknown", 50)
    assert "No ingredients" in summary
