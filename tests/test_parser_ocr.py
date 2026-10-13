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
