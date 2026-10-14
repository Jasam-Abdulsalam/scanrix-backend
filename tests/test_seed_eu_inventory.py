from scripts.seed_eu_inventory import (
    cas_numbers, inventory_name, load_inventory, parse_functions, unique_cas_owners,
)


def test_functions_are_lowercased_split_and_deduplicated():
    assert parse_functions("Emulsifying/ skin  conditioning/Emulsifying") == ["emulsifying", "skin conditioning"]
    assert parse_functions("") == [] and parse_functions(None) == []


def test_name_is_normalised_like_label_text_and_overlong_names_are_dropped():
    assert inventory_name({"INCI name": "ABIETYL  ALCOHOL"}) == "abietyl alcohol"
    assert inventory_name({"INCI name": "X" * 150}) == ""


def test_cas_numbers_are_extracted_from_slash_lists():
    assert cas_numbers({"CAS No": "9006-65-9/63148-62-9"}) == ["9006-65-9", "63148-62-9"]
    assert cas_numbers({"CAS No": ""}) == []


def test_shared_cas_numbers_are_not_assigned_to_any_name():
    rows = [
        {"INCI name": "ABIES PECTINATA EXTRACT", "CAS No": "92128-34-2"},
        {"INCI name": "ABIES PECTINATA OIL", "CAS No": "92128-34-2"},
        {"INCI name": "ABIETIC ACID", "CAS No": "514-10-3"},
    ]
    assert unique_cas_owners(rows) == {"514-10-3": "abietic acid"}


def test_real_file_contains_the_everyday_ingredients_that_were_unknown():
    names = {inventory_name(r) for r in load_inventory()}
    assert {"glycerin", "stearic acid", "edta", "disodium edta"} <= names
