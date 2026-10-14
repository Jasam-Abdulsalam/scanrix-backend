import asyncio
import json
from collections import Counter

from scripts import extract_fssai as ex
from scripts import seed_fssai as seed
from app.services.rule_engine import rule_engine


def test_ins_tokens_expand_to_matching_codes():
    assert ex.expand_ins("322(i), (ii)") == ["322i", "322ii"]
    assert ex.expand_ins("150a") == ["150a"]
    assert ex.expand_ins("450 (vi)") == ["450vi"]
    assert ex.expand_ins("954(i)") == ["954i"]


def test_table_rows_and_annexure_rows_are_read_but_levels_are_not_mistaken_for_ins():
    table = ["Allura red AC 129 100 mg/kg 52", "Lecithins 322(i), (ii) GMP", "Curcumin 100 100 mg/kg", "Brilliant blue FCF 133 100 mg/kg 52"]
    annex = ["Group Name Additive Name INS", "Sodium benzoate 211", "=====PAGE 3====="]
    assert ex.extract_ins(table, annex) == {"129", "322i", "322ii", "100", "133", "211"}


def test_sections_ignore_category_descriptions_before_part_iv():
    lines = ["6.8.2 something 123", "IV. USE OF FOOD ADDITIVES IN FOOD PRODUCTS", "x 211 GMP", "Annexure-1", "Sodium benzoate 211", "ANNEX TO GMP Table", "junk 999"]
    tables, annex = ex.split_sections(lines)
    assert ex.extract_ins(tables, annex) == {"211"}


def test_extracted_file_is_a_sane_positive_list():
    codes = set(seed.load_codes())
    assert len(codes) > 250 and {"102", "211", "322i", "450vi"} <= codes
    assert not {"924", "952"} & codes  # absent from the tables; must never be used as a "banned" claim


def test_ins_maps_to_the_e_code_ingredient_key():
    assert seed.ingredient_key("450vi") == "e450vi"


def test_seed_marks_only_known_additives(monkeypatch):
    known = {"e102": "ing1"}
    marked = []

    async def fake_find(db, key):
        return known.get(key)

    async def fake_fact(db, ing_id, source_id, dim, value, **kw):
        marked.append((ing_id, dim, value, kw["severity"], kw["applies_to"]))

    async def fake_source(db, **kw):
        return "src"

    monkeypatch.setattr(seed, "find_ingredient_id", fake_find)
    monkeypatch.setattr(seed, "upsert_fact", fake_fact)
    monkeypatch.setattr(seed, "upsert_source", fake_source)
    monkeypatch.setattr(seed, "load_codes", lambda: ["102", "999"])
    stats = asyncio.run(seed.seed_fssai(None))
    assert marked == [("ing1", "permitted_regions", "india_fssai", "none", "food")]
    assert stats == Counter({"marked_permitted_in_india": 1, "not_in_our_database": 1})


def test_regional_note_shows_up_without_changing_severity():
    fact = {"dimension": "permitted_regions", "value": "india_fssai", "severity": "none", "evidence_tier": 1,
            "conditions": seed.NOTE}
    result = rule_engine.evaluate([{"raw_name": "x", "canonical_name": "x", "matched": True,
                                    "match_type": "exact", "confidence": 1.0, "facts": [fact]}])
    finding = result.findings[0]
    assert finding.notes == [seed.NOTE] and finding.severity == "none" and finding.flags == []
