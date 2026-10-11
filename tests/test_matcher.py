import asyncio
from app.services.ingredient_matcher import IngredientMatcher

async def run_matcher_tests():
    matcher = IngredientMatcher()

    # Pre-populate simulated alias cache (no database needed for this test!)
    matcher._alias_map = {
        "acrylamide": "id_acrylamide",
        "sodium nitrite": "id_nitrite",
        "e250": "id_nitrite",
        "titanium dioxide": "id_tio2",
        "ci 77891": "id_tio2",
        "aqua": "id_water",
        "water": "id_water"
    }
    matcher._all_aliases = list(matcher._alias_map.keys())
    matcher._is_loaded = True

    print("🧪 Running Ingredient Matcher Tests...")

    # 1. Exact match test
    res_exact = await matcher.match("acrylamide")
    assert res_exact.match_type == "exact"
    assert res_exact.ingredient_id == "id_acrylamide"
    assert res_exact.confidence == 1.0
    print("  ✅ Exact match passed ('acrylamide')")

    # 2. Alias match test (E-number and INCI)
    res_enum = await matcher.match("e250")
    assert res_enum.match_type == "exact"
    assert res_enum.ingredient_id == "id_nitrite"

    res_inci = await matcher.match("ci 77891")
    assert res_inci.match_type == "exact"
    assert res_inci.ingredient_id == "id_tio2"
    print("  ✅ Alias match passed ('e250' -> Sodium Nitrite, 'ci 77891' -> Titanium Dioxide)")

    # 3. Fuzzy match test (OCR Typo: 'acrylamlde' with an 'l' instead of 'i')
    res_fuzzy = await matcher.match("acrylamlde")
    assert res_fuzzy.match_type == "fuzzy"
    assert res_fuzzy.ingredient_id == "id_acrylamide"
    assert res_fuzzy.confidence >= 0.90
    print(f"  ✅ Fuzzy typo match passed ('acrylamlde' matched 'acrylamide' with {res_fuzzy.confidence*100}% confidence)")

    # 4. Unknown ingredient test
    res_unknown = await matcher.match("quantum super molecule xyz")
    assert res_unknown.match_type == "unknown"
    assert res_unknown.ingredient_id is None
    assert res_unknown.confidence == 0.0
    print("  ✅ Unknown rejection passed (correctly sent to AI fallback)")

    print("🎉 All matcher tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_matcher_tests())
