import json
from pathlib import Path

from scripts.seed_aliases import CURATED_PATH, load_entries, matching_form, validate_entries


def test_matching_form_matches_what_the_parser_produces():
    assert matching_form("FD&C Yellow No. 5") == "fd&c yellow no 5"
    assert matching_form("CI 19140") == "ci 19140"
    assert matching_form("  Aqua ") == "aqua"


def test_duplicate_alias_under_two_ingredients_is_rejected():
    entries = [{"canonical": "a", "aliases": ["x y"]}, {"canonical": "b", "aliases": ["X  Y."]}]
    try:
        validate_entries(entries)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "x y" in str(e)


def test_empty_alias_is_rejected():
    try:
        validate_entries([{"canonical": "a", "aliases": ["..."]}])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_committed_file_is_valid_and_already_in_matching_form():
    entries = load_entries()
    validated = validate_entries(entries)  # no conflicts or empties
    for entry, (_, forms) in zip(entries, validated):
        assert entry["aliases"] == forms, f"{entry['canonical']}: store aliases in matching form"
        assert entry["basis"], f"{entry['canonical']}: every entry needs a basis"


def test_targets_exist_in_the_open_food_facts_seed_when_available():
    """Every canonical target must be an ingredient the OFF seed creates (skipped if files absent)."""
    off = Path(CURATED_PATH).parent.parent / "raw" / "off"
    if not (off / "additives.json").exists():
        return
    from scripts.common import normalize_name
    from scripts.seed_off import english_name, load_taxonomy
    codes = {normalize_name(k.removeprefix("en:")) for k in load_taxonomy("additives")}
    names = {english_name(v) for v in load_taxonomy("ingredients").values() if "e_number" not in v}
    missing = [e["canonical"] for e in load_entries() if e["canonical"] not in codes | names]
    assert missing == [], f"targets not created by the OFF seed: {missing}"
