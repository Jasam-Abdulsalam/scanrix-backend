from app.services.rule_engine import rule_engine


def _item(facts, matched=True):
    return {"raw_name": "x", "canonical_name": "x", "matched": matched,
            "match_type": "exact" if matched else "unknown", "confidence": 1.0, "facts": facts}


def test_function_fact_is_recognised_but_never_a_warning():
    fact = {"dimension": "function", "value": "emulsifier, humectant", "severity": "none", "evidence_tier": 3}
    result = rule_engine.evaluate([_item([fact])])
    finding = result.findings[0]
    assert finding.severity == "none"
    assert finding.flags == []
    assert finding.evidence_tier is None  # no tier badge for plain information
    assert finding.functions == ["emulsifier", "humectant"]
    assert result.recognised_count == 1 and result.coverage == 1.0
    assert result.overall_severity == "none"


def test_function_fact_even_with_default_severity_cannot_raise_a_warning():
    fact = {"dimension": "function", "value": "preservative"}  # severity missing -> engine default 'medium'
    assert rule_engine.evaluate([_item([fact])]).overall_severity == "none"


def test_allergen_info_is_low_severity_with_a_label():
    fact = {"dimension": "allergen", "value": "allergen_info:milk", "severity": "low", "evidence_tier": 3}
    finding = rule_engine.evaluate([_item([fact])]).findings[0]
    assert finding.severity == "low"
    assert "Contains a common allergen" in finding.flags


def test_hazard_still_wins_next_to_function_facts():
    facts = [
        {"dimension": "function", "value": "preservative", "severity": "none", "evidence_tier": 3},
        {"dimension": "cancer_class", "value": "Group 1", "severity": "critical", "evidence_tier": 2},
    ]
    result = rule_engine.evaluate([_item(facts)])
    assert result.overall_severity == "critical"
    assert result.findings[0].evidence_tier == 2
