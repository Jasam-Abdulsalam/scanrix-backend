from app.services.ingredient_parser import ingredient_parser

def test_basic_parsing():
    raw = "Water, Sugar, Salt"
    result = ingredient_parser.parse(raw)
    names = [i.clean_name for i in result.ingredients]
    assert names == ["water", "sugar", "salt"]
    print("✅ test_basic_parsing passed!")

def test_prefix_removal():
    raw = "Ingredients: Water, Cane Sugar, Sea Salt."
    result = ingredient_parser.parse(raw)
    names = [i.clean_name for i in result.ingredients]
    assert names == ["water", "cane sugar", "sea salt"]
    print("✅ test_prefix_removal passed!")

def test_sub_ingredients_and_brackets():
    raw = "Enriched Flour (Wheat Flour, Niacin, Reduced Iron), Vegetable Oil (Palm Oil), Salt"
    result = ingredient_parser.parse(raw)
    
    flour = result.ingredients[0]
    assert flour.clean_name == "enriched flour"
    assert "wheat flour" in flour.sub_ingredients
    assert "niacin" in flour.sub_ingredients
    
    oil = result.ingredients[1]
    assert oil.clean_name == "vegetable oil"
    assert oil.sub_ingredients == ["palm oil"]
    print("✅ test_sub_ingredients_and_brackets passed!")

def test_percentage_extraction():
    raw = "Cocoa Butter (15%), Sugar, Whole Milk Powder (25.5%)"
    result = ingredient_parser.parse(raw)
    
    assert result.ingredients[0].clean_name == "cocoa butter"
    assert result.ingredients[0].percentage == 15.0
    
    assert result.ingredients[2].clean_name == "whole milk powder"
    assert result.ingredients[2].percentage == 25.5
    print("✅ test_percentage_extraction passed!")

def test_advisory_allergen_extraction():
    raw = "Wheat Flour, Sugar, Palm Oil. May contain traces of: peanuts, tree nuts, sesame."
    result = ingredient_parser.parse(raw)
    
    names = [i.clean_name for i in result.ingredients]
    assert names == ["wheat flour", "sugar", "palm oil"]
    assert "peanuts" in result.allergens_declared
    assert "tree nuts" in result.allergens_declared
    assert "sesame" in result.allergens_declared
    print("✅ test_advisory_allergen_extraction passed!")

def test_ocr_noise():
    raw = "• Ingredients:\nWater\n• Sugar\n* Preservative (E250) •"
    result = ingredient_parser.parse(raw)
    names = [i.clean_name for i in result.ingredients]
    assert "water" in names
    assert "sugar" in names
    print("✅ test_ocr_noise passed!")

if __name__ == "__main__":
    print("🧪 Running Ingredient Parser Tests...")
    test_basic_parsing()
    test_prefix_removal()
    test_sub_ingredients_and_brackets()
    test_percentage_extraction()
    test_advisory_allergen_extraction()
    test_ocr_noise()
    print("🎉 All parser tests passed successfully!")
