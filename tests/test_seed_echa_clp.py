import asyncio
from collections import Counter
from datetime import date

from scripts import seed_echa_clp as echa
from scripts.xlsx_reader import read_sheet


def test_codes_become_health_effects_and_other_hazards_are_dropped():
    assert echa.effects_from_codes("H315\nH317\nH319") == {"skin_irritation", "skin_allergy", "eye_irritation"}
    assert echa.effects_from_codes("H360FD\nH350i") == {"reproductive", "carcinogenic"}
    assert echa.effects_from_codes("H225\nH400\nH410") == set()  # flammable / aquatic: not shown
    assert echa.effects_from_codes("") == set()


def test_description_is_plain_english_and_deduplicated():
    text = echa.describe({"organ_damage", "skin_irritation"})
    assert "Can irritate the skin" in text and "damage to organs" in text


def test_future_entries_are_not_in_force():
    assert echa.is_in_force({"In application": "40513"}, today=date(2026, 10, 14))
    assert not echa.is_in_force({"In application": "47150"}, today=date(2026, 10, 14))  # 2029-01-01
    assert echa.is_in_force({}, today=date(2026, 10, 14))


def test_multi_substance_entry_is_split_into_clean_names():
    row = {"Chemical Name": "boric acid [1]\northoboric acid, sodium salt [2]; borax"}
    assert echa.entry_names(row) == ["boric acid", "orthoboric acid, sodium salt", "borax"]


def test_effects_attach_only_to_known_ingredients_and_merge_per_ingredient(monkeypatch):
    known = {"122-99-6": "ing1", "citric acid": "ing2"}

    async def fake_find(db, key):
        return known.get(key)

    monkeypatch.setattr(echa, "find_ingredient_id", fake_find)
    entries = [
        {"Chemical Name": "2-phenoxyethanol", "CAS No": "122-99-6", "Classification Hazard Statement Code(s)": "H318"},
        {"Chemical Name": "2-phenoxyethanol", "CAS No": "122-99-6", "Classification Hazard Statement Code(s)": "H335"},
        {"Chemical Name": "unknown chemical", "CAS No": "1-1-1", "Classification Hazard Statement Code(s)": "H315"},
        {"Chemical Name": "citric acid", "CAS No": "", "Classification Hazard Statement Code(s)": "H225"},
    ]
    stats = Counter()
    found = asyncio.run(echa.collect_effects(None, entries, stats))
    assert found == {"ing1": {"eye_damage", "respiratory_irritation"}}
    assert stats["entries_not_in_our_database"] == 1


def test_xlsx_reader_parses_the_real_file():
    rows = read_sheet(echa.ECHA_FILE, "xl/worksheets/sheet1.xml", echa.HEADER_ROW)
    assert len(rows) > 4000 and "Chemical Name" in rows[0]
