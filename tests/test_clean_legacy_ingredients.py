from scripts.clean_legacy_ingredients import clean_ingredients

BAD = {"name": "salt", "purpose": "Common ingredient", "safety_rating": 40,
       "concerns": ["Contains trans fats"], "is_natural": True}
GOOD = {"name": "aqua", "purpose": "Solvent", "safety_rating": 90, "concerns": [], "is_natural": False}


def test_legacy_fields_are_reset_and_name_is_kept():
    out, n = clean_ingredients([BAD])
    assert n == 1
    assert out == [{"name": "salt", "purpose": None, "safety_rating": 50, "concerns": [], "is_natural": True}]


def test_other_ingredients_are_untouched_and_a_second_run_changes_nothing():
    out, n = clean_ingredients([BAD, GOOD])
    assert out[1] is GOOD and n == 1
    again, n2 = clean_ingredients(out)
    assert again == out and n2 == 0
