"""Parser rules for messy OCR text (page noise, lost commas, blends, duplicates)."""
from app.services.ingredient_parser import ingredient_parser

# Modelled on a real screenshot OCR of a face wash label (see 2026-10-13 test run).
MESSY = (
    "11:52 www.catchnpack.pk Ingredients: Aqua, Ammonium Lauryl Sulfate, Stearic Acid, Glycerin, "
    "Glyceryl Stearate & PEG-100 Stearate, Phenoxyethanol, "
    "Coco.Glucoside & Glyceryl Oleate Methylchloroisothiazolinone & Methyl iso thiazolinone. Menthol, "
    "Glycerin, CI 19140. CI 42053. Acrylates CHO 50 Alky Arylate Crosspolyme AA Q Save Visit Moisturising "
    "Aloe Vera Face Qhimalaya face wash"
)


def _names(text):
    return [i.clean_name for i in ingredient_parser.parse(text).ingredients]


def test_text_before_ingredients_marker_is_dropped():
    names = _names(MESSY)
    assert names[0] == "aqua"
    assert not any("catchnpack" in n or "11" in n for n in names)


def test_blend_ampersand_splits_into_two():
    names = _names(MESSY)
    assert "glyceryl stearate" in names and "peg-100 stearate" in names


def test_sentence_period_splits_but_decimals_do_not():
    names = _names(MESSY)
    assert "menthol" in names
    assert "ci 19140" in names and "ci 42053" in names
    assert _names("Ingredients: Retinol 2.5%, Water")[:2] == ["retinol", "water"]


def test_duplicates_are_removed_keeping_first():
    names = _names(MESSY)
    assert names.count("glycerin") == 1


def test_noise_is_discarded_not_treated_as_ingredient():
    result = ingredient_parser.parse(MESSY)
    assert any("Acrylates" in d for d in result.discarded)
    assert not any("acrylates cho" in i.clean_name for i in result.ingredients)


def test_long_sub_ingredient_list_is_not_noise():
    text = "Ingredients: Enriched Flour (Wheat Flour, Niacin, Reduced Iron, Thiamine Mononitrate, Riboflavin, Folic Acid), Sugar"
    result = ingredient_parser.parse(text)
    assert result.discarded == []
    assert result.ingredients[0].clean_name == "enriched flour"
    assert "niacin" in result.ingredients[0].sub_ingredients


def test_marker_without_colon_still_anchors():
    assert _names("Page header Ingredients Aqua, Glycerin")[0] == "aqua"


def test_bullets_separate_ingredients_but_wrapped_lines_do_not():
    p = ingredient_parser
    assert [i.clean_name for i in p.parse("• Ingredients:\nWater\n• Sugar\n* Preservative (E250) •").ingredients] == \
        ["water", "sugar", "preservative"]
    assert [i.clean_name for i in p.parse("Ingredients: water, sodium laureth\nsulfate, glycerin").ingredients] == \
        ["water", "sodium laureth sulfate", "glycerin"]
    assert [i.clean_name for i in p.parse("Ingredients: sugar*, salt").ingredients] == ["sugar", "salt"]  # footnote star


def test_contains_declaration_is_separated_from_the_list():
    r = ingredient_parser.parse("Ingredients: Water, Sugar. Contains: Milk and Soy. May contain traces of nuts.")
    assert [i.clean_name for i in r.ingredients] == ["water", "sugar"]
    assert r.contains_declared == ["milk", "soy"] and r.allergens_declared == ["nuts"]


def test_contains_is_not_confused_with_other_phrases():
    p = ingredient_parser
    assert p.parse("Ingredients: sugar, flour (contains milk), cocoa").contains_declared == []
    assert [i.clean_name for i in p.parse("Contains: water, sugar, salt").ingredients] == ["water", "sugar", "salt"]
    less = p.parse("Ingredients: Water. Contains less than 2% of: salt, citric acid")
    assert [i.clean_name for i in less.ingredients] == ["water", "salt", "citric acid"] and less.contains_declared == []
    assert p.parse("Ingredients: sugar. Contains: store in a cool place").contains_declared == []


# Real Maggi screenshot OCR (2026-10-19): OCR lost a ")" in "Wheat flour (Atal (86 2%)," so the bracket
# looked open for the rest of the label, the whole text became ONE token and every ingredient was lost.
UNBALANCED = (
    "INGReDIeNTS Wheat flour (Atal (86 2%), Pal oll, lodized salt. Wheat gluten, Thickeners (508 &412), "
    "Acidity regulators (S010) & 500 ( AA Noodles: Sugar, Starch, Palm oil, Thickener (508), "
    "Flavour enhancer (635). Colour (150d). Wheat gluten and Mineral. May Contains Millk Oats & Soy."
)


def test_a_lost_closing_bracket_does_not_swallow_the_rest_of_the_list():
    names = _names(UNBALANCED)
    assert "starch" in names and "palm oil" in names and "lodized salt" in names   # was: names == []
    assert len(names) >= 8


def test_balanced_text_is_unchanged_by_bracket_repair():
    text = "Sugar, Flour (Wheat, Salt), Cocoa"
    assert ingredient_parser.drop_unmatched_openers(text) == text
    r = ingredient_parser.parse("Ingredients: " + text)
    assert [i.clean_name for i in r.ingredients] == ["sugar", "flour", "cocoa"]
    assert r.ingredients[1].sub_ingredients == ["wheat", "salt"]
