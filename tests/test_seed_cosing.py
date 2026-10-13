import asyncio

from app.services.ingredient_db_service import ingredient_db_service
from app.services.ingredient_matcher import ingredient_matcher
from app.services.rule_engine import rule_engine
from scripts.seed_cosing import conditions_text, fact_for, split_cas, split_names


def test_split_names_handles_lists_colour_codes_and_internal_slashes():
    assert split_names("AMMONIUM BENZOATE / BUTYL BENZOATE") == ["ammonium benzoate", "butyl benzoate"]
    assert split_names("CI 42053/ FAST GREEN FCF") == ["ci 42053", "fast green fcf"]
    assert split_names("CI 42090/ ACID BLUE 9; ACID BLUE 9 ALUMINUM LAKE") == ["ci 42090", "acid blue 9", "acid blue 9 aluminum lake"]
    assert split_names("PEG/PPG-17/6 COPOLYMER") == ["peg/ppg-17/6 copolymer"]  # slash inside a name is kept
    assert split_names("") == []


def test_split_cas_ignores_placeholders():
    assert split_cas("70643-19-5 / 66422-95-5") == ["70643-19-5", "66422-95-5"]
    assert split_cas("-") == []


def test_allowed_lists_are_functions_never_warnings():
    row = {"Name of Common Ingredients Glossary": "PHENOXYETHANOL", "Maximum concentration in ready for use preparation": "1.0%"}
    fact = fact_for("V", row)
    assert (fact["dimension"], fact["value"], fact["severity"]) == ("function", "preservative", "none")
    assert "1.0%" in fact["conditions"]
    assert fact_for("IV", row)["value"] == "colourant" and fact_for("VI", row)["value"] == "UV filter"


def test_annex_iii_general_restriction_is_low_but_use_specific_is_information_only():
    general = fact_for("III", {"Product Type, body parts": "", "Maximum concentration in ready for use preparation": "0.1%"})
    assert (general["value"], general["severity"]) == ("cosmetics_restricted_eu", "low")
    hair = fact_for("III", {"Product Type, body parts": "Hair dye substance in oxidative hair dye products"})
    assert (hair["value"], hair["severity"]) == ("cosmetics_restricted_in_specific_use_eu", "none")


def test_annex_ii_is_critical_only_without_a_use_qualifier():
    plain = fact_for("II", {"Chemical name / INN": "Spironolactone (INN)"})
    assert (plain["value"], plain["severity"]) == ("cosmetics_banned_eu", "critical")
    for name in ("3-Nitro-4-aminophenoxyethanol and its salts, when used as a substance in hair dye products",
                 "Mercury and its compounds, except those special cases included in Annex V"):
        fact = fact_for("II", {"Chemical name / INN": name})
        assert (fact["value"], fact["severity"]) == ("cosmetics_banned_in_specific_use_eu", "none")


def test_conditions_text_is_whitespace_clean_and_capped():
    row = {"Other": "- Do not use\n  with nitrosating\xad agents " * 40}
    text = conditions_text(row)
    assert "\n" not in text and "\xad" not in text and len(text) <= 500


def _evaluate(value, severity):
    fact = {"dimension": "regulatory", "value": value, "severity": severity, "evidence_tier": 1}
    return rule_engine.evaluate([{"raw_name": "x", "canonical_name": "x", "matched": True,
                                  "match_type": "exact", "confidence": 1.0, "facts": [fact]}])


def test_engine_flags_banned_critical_and_restricted_low_without_crossing_rules():
    banned = _evaluate("cosmetics_banned_eu", "critical")
    assert banned.overall_severity == "critical"
    assert banned.findings[0].flags == ["Listed as prohibited in EU cosmetics (Annex II)"]
    restricted = _evaluate("cosmetics_restricted_eu", "low")
    assert restricted.overall_severity == "low"
    assert restricted.findings[0].flags == ["Restricted in EU cosmetics (Annex III)"]  # not also the banned rule


def test_use_specific_information_is_not_a_finding():
    result = _evaluate("cosmetics_banned_in_specific_use_eu", "none")
    assert result.overall_severity == "none"
    assert result.findings[0].flags == []
    assert result.dimensions["regulatory"].findings_count == 0
    assert result.dimensions["regulatory"].flagged_ingredients == []


class _FakeFacts:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, projection=None):
        wanted = set(query["ingredient_id"]["$in"])

        async def gen():
            for d in self._docs:
                if d["ingredient_id"] in wanted:
                    yield dict(d)
        return gen()


class _FakeDB:
    def __init__(self, docs):
        self.facts = _FakeFacts(docs)


def test_cosmetic_only_facts_do_not_apply_to_food(monkeypatch):
    monkeypatch.setattr(ingredient_matcher, "_alias_map", {"spironolactone": "id_x"})
    monkeypatch.setattr(ingredient_matcher, "_all_aliases", ["spironolactone"])
    monkeypatch.setattr(ingredient_matcher, "_is_loaded", True)
    db = _FakeDB([{"ingredient_id": "id_x", "dimension": "regulatory", "value": "cosmetics_banned_eu",
                   "severity": "critical", "evidence_tier": 1, "applies_to": "cosmetic"}])
    food, _ = asyncio.run(ingredient_db_service.analyze_ingredients_text("spironolactone", category="food", db=db))
    cosmetic, _ = asyncio.run(ingredient_db_service.analyze_ingredients_text("spironolactone", category="cosmetic", db=db))
    assert food.overall_severity == "none" and food.findings[0].matched is True
    assert cosmetic.overall_severity == "critical"
