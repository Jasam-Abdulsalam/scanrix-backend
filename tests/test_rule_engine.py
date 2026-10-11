from app.services.rule_engine import rule_engine

def test_pure_function_determinism():
    sample_input = [
        {
            "raw_name": "Acrylamide",
            "canonical_name": "acrylamide",
            "matched": True,
            "match_type": "exact",
            "confidence": 1.0,
            "facts": [
                {
                    "dimension": "cancer_class",
                    "value": "Group 2A",
                    "severity": "high",
                    "evidence_tier": 2
                }
            ]
        },
        {
            "raw_name": "Water",
            "canonical_name": "water",
            "matched": True,
            "match_type": "exact",
            "confidence": 1.0,
            "facts": []
        }
    ]

    res1 = rule_engine.evaluate(sample_input)
    res2 = rule_engine.evaluate(sample_input)

    assert res1.overall_severity == res2.overall_severity == "high"
    assert res1.coverage == res2.coverage == 1.0
    assert len(res1.findings) == len(res2.findings) == 2
    print("✅ test_pure_function_determinism passed!")

def test_coverage_and_unknown_handling():
    # 4 ingredients: 3 recognised, 1 unknown
    sample_input = [
        {"raw_name": "Sugar", "canonical_name": "sugar", "matched": True, "match_type": "exact", "confidence": 1.0, "facts": []},
        {"raw_name": "Salt", "canonical_name": "salt", "matched": True, "match_type": "exact", "confidence": 1.0, "facts": []},
        {"raw_name": "Cocoa", "canonical_name": "cocoa", "matched": True, "match_type": "exact", "confidence": 1.0, "facts": []},
        {"raw_name": "Secret Mystery Herb", "canonical_name": None, "matched": False, "match_type": "unknown", "confidence": 0.0, "facts": []}
    ]

    res = rule_engine.evaluate(sample_input)

    assert res.total_count == 4
    assert res.recognised_count == 3
    assert res.coverage == 0.75  # 75% coverage
    
    unknown_finding = res.findings[3]
    assert unknown_finding.matched is False
    assert unknown_finding.severity == "none"  # Not marked safe!
    print("✅ test_coverage_and_unknown_handling passed!")

def test_worst_severity_ranking():
    sample_input = [
        {
            "raw_name": "Asbestos",  # Group 1 (Critical)
            "canonical_name": "asbestos",
            "matched": True,
            "match_type": "exact",
            "confidence": 1.0,
            "facts": [{"dimension": "cancer_class", "value": "Group 1", "severity": "critical", "evidence_tier": 2}]
        },
        {
            "raw_name": "Aloe vera whole extract",  # Group 2B (Medium)
            "canonical_name": "aloe vera whole leaf extract",
            "matched": True,
            "match_type": "exact",
            "confidence": 1.0,
            "facts": [{"dimension": "cancer_class", "value": "Group 2B", "severity": "medium", "evidence_tier": 2}]
        }
    ]

    res = rule_engine.evaluate(sample_input)

    # Worst severity in cancer dimension must be critical
    cancer_dim = res.dimensions["cancer_class"]
    assert cancer_dim.worst_severity == "critical"
    assert cancer_dim.findings_count == 2
    assert "Asbestos" in cancer_dim.flagged_ingredients
    assert "Aloe vera whole extract" in cancer_dim.flagged_ingredients
    assert res.overall_severity == "critical"
    print("✅ test_worst_severity_ranking passed!")

def test_non_additive_severity():
    # Having multiple medium ingredients must NOT add up to high/critical
    sample_input = [
        {"raw_name": "Item 1", "canonical_name": "i1", "matched": True, "match_type": "exact", "confidence": 1.0, "facts": [{"dimension": "allergen", "value": "major_allergen", "severity": "medium", "evidence_tier": 2}]},
        {"raw_name": "Item 2", "canonical_name": "i2", "matched": True, "match_type": "exact", "confidence": 1.0, "facts": [{"dimension": "allergen", "value": "major_allergen", "severity": "medium", "evidence_tier": 2}]},
        {"raw_name": "Item 3", "canonical_name": "i3", "matched": True, "match_type": "exact", "confidence": 1.0, "facts": [{"dimension": "allergen", "value": "major_allergen", "severity": "medium", "evidence_tier": 2}]}
    ]

    res = rule_engine.evaluate(sample_input)

    allergen_dim = res.dimensions["allergen"]
    assert allergen_dim.worst_severity == "medium"
    assert res.overall_severity == "medium"
    print("✅ test_non_additive_severity passed!")

if __name__ == "__main__":
    print("🧪 Running Rule Engine Tests...")
    test_pure_function_determinism()
    test_coverage_and_unknown_handling()
    test_worst_severity_ranking()
    test_non_additive_severity()
    print("🎉 All rule engine tests passed successfully!")
