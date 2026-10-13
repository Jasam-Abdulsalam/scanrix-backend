from scripts.seed_off import allergen_name, english_name, parse_functions, resolve_allergens


def test_english_name_strips_additive_code_prefix():
    assert english_name({"name": {"en": "E450vi - Dicalcium diphosphate"}}) == "dicalcium diphosphate"
    assert english_name({"name": {"en": "Turmeric"}}) == "turmeric"
    assert english_name({"name": {"fr": "curcuma"}}) is None  # English only


def test_parse_functions():
    entry = {"additives_classes": {"en": "en:emulsifier, en:humectant, en:flavour-enhancer"}}
    assert parse_functions(entry) == ["emulsifier", "humectant", "flavour enhancer"]
    assert parse_functions({}) == []


def test_allergen_name():
    assert allergen_name("en:sesame-seeds") == "sesame seeds"


def test_allergens_are_inherited_through_parents():
    taxonomy = {
        "en:milk-proteins": {"allergens": {"en": "en:milk"}, "parents": ["en:dairy"]},
        "en:dairy": {},
        "en:casein": {"parents": ["en:milk-proteins"]},
        "en:wheat": {"allergens": {"en": "en:gluten"}},
        "en:sugar": {},
    }
    result = resolve_allergens(taxonomy, {"en:milk", "en:gluten"})
    assert result["en:casein"] == ["milk"]
    assert result["en:milk-proteins"] == ["milk"]
    assert result["en:wheat"] == ["gluten"]
    assert "en:sugar" not in result and "en:dairy" not in result


def test_unlisted_allergen_ids_and_cycles_are_ignored():
    taxonomy = {
        "en:a": {"allergens": {"en": "en:none"}, "parents": ["en:b"]},
        "en:b": {"parents": ["en:a"]},  # cycle
    }
    assert resolve_allergens(taxonomy, {"en:milk"}) == {}
