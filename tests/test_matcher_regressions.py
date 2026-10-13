"""Regressions found in the 2026-10-12 end-to-end run against the real alias data."""
import asyncio

from app.services.ingredient_db_service import ingredient_db_service
from app.services.ingredient_matcher import IngredientMatcher, ingredient_matcher

# Real alias strings from the Prop 65 seed that used to be matched by substring.
ALIASES = {
    "chlorinated drinking-water": "id_cdw",
    "bromacil lithium salt": "id_bls",
    "iron sorbitol-citric acid complex": "id_iscac",
    "methyl bromide, as a structural fumigant": "id_mb",
    "formaldehyde": "id_formaldehyde",
    "water": "id_water",
}


def _matcher() -> IngredientMatcher:
    m = IngredientMatcher()
    m._alias_map = dict(ALIASES)
    m._all_aliases = list(ALIASES)
    m._is_loaded = True
    return m


def test_common_words_are_not_matched_inside_long_chemical_names():
    m = _matcher()
    for word in ("salt", "citric acid", "natural", "sugar"):
        res = asyncio.run(m.match(word))
        assert res.ingredient_id is None, f"{word!r} wrongly matched {res.matched_alias!r}"


def test_exact_short_word_still_matches():
    res = asyncio.run(_matcher().match("water"))
    assert (res.match_type, res.ingredient_id) == ("exact", "id_water")


def test_real_typo_still_matches():
    res = asyncio.run(_matcher().match("formaldehyd"))  # one letter missing
    assert res.match_type == "fuzzy"
    assert res.ingredient_id == "id_formaldehyde"


def test_low_confidence_suggestion_is_not_accepted():
    res = asyncio.run(_matcher().match("formaldehydes inc"))
    assert res.ingredient_id is None  # never accepted without a score >= 90


class _FakeFacts:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, projection=None):
        wanted = set(query["ingredient_id"]["$in"])

        async def gen():
            for d in self._docs:
                if d["ingredient_id"] in wanted:
                    yield d

        return gen()


class _FakeDB:
    def __init__(self, docs):
        self.facts = _FakeFacts(docs)


def test_bracketed_descriptor_does_not_inherit_facts_from_a_fuzzy_match(monkeypatch):
    """'Xyzzy Flavour (natural)' used to inherit a Prop 65 developmental flag."""
    real = _matcher()
    monkeypatch.setattr(ingredient_matcher, "_alias_map", real._alias_map)
    monkeypatch.setattr(ingredient_matcher, "_all_aliases", real._all_aliases)
    monkeypatch.setattr(ingredient_matcher, "_is_loaded", True)
    db = _FakeDB([
        {"ingredient_id": "id_mb", "dimension": "developmental",
         "value": "developmental_toxicity", "severity": "high", "evidence_tier": 2},
    ])

    evaluation, unknown = asyncio.run(
        ingredient_db_service.analyze_ingredients_text("Xyzzy Flavour (natural), Salt", db=db)
    )

    flavour = evaluation.findings[0]
    assert flavour.matched is False
    assert flavour.severity == "none"
    assert flavour.flags == []
    assert evaluation.overall_severity == "none"
    assert evaluation.recognised_count == 0
    assert set(unknown) == {"xyzzy flavour", "salt"}


def test_exact_sub_ingredient_still_contributes_its_facts(monkeypatch):
    real = _matcher()
    monkeypatch.setattr(ingredient_matcher, "_alias_map", real._alias_map)
    monkeypatch.setattr(ingredient_matcher, "_all_aliases", real._all_aliases)
    monkeypatch.setattr(ingredient_matcher, "_is_loaded", True)
    db = _FakeDB([
        {"ingredient_id": "id_formaldehyde", "dimension": "cancer_class",
         "value": "group_1", "severity": "critical", "evidence_tier": 2},
    ])

    evaluation, _ = asyncio.run(
        ingredient_db_service.analyze_ingredients_text("Preservative Mix (formaldehyde)", db=db)
    )
    assert evaluation.findings[0].severity != "none"
