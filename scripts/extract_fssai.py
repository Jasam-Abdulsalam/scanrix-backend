"""
ONE-TIME, developer-only: extracts the INS numbers of additives named in FSSAI's Food Additives
tables (Appendix A of the Food Products Standards and Food Additives Regulations, 2011) into
data/curated/fssai_permitted_ins.json. The seed (scripts/seed_fssai.py) reads that JSON, so the
Docker image never needs a PDF library.

Needs `pypdf` (NOT in requirements.txt):
    python3 -m venv /tmp/pdfenv && /tmp/pdfenv/bin/pip install pypdf
    PYTHONPATH=. /tmp/pdfenv/bin/python -m scripts.extract_fssai

Completeness: a POSITIVE list only. An additive missing from it must never be reported as "not
permitted": text extraction from the flattened multi-column tables can miss entries.
"""
import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Set

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "data" / "raw" / "fssai" / "Appendix A(4).pdf"
OUT_PATH = ROOT / "data" / "curated" / "fssai_permitted_ins.json"

INS = r"\d{3,4}[a-z]?(?:\s?\([ivx]+\))?(?:\s*,\s*\(?[ivx]+\)?)*"           # 150a | 322(i), (ii) | 450 (vi)
LEVEL = r"(?:GMP|\d[\d,\.]*\s*(?:mg/kg|g/kg|mg/l|ml/kg|%|ppm|mg/L|mg/ l))"   # a maximum level follows the INS
TABLE_ROW = re.compile(r"(?:^|\s)(" + INS + r")\s+" + LEVEL)
ANNEX_ROW = re.compile(r"\s(" + INS + r")\s*$")                              # "Sodium benzoate 211"
INS_PARTS = re.compile(r"(\d{3,4}[a-z]?)(\([ivx]+\))?((?:,\(?[ivx]+\)?)*)$")


def expand_ins(token: str) -> List[str]:
    """'322(i), (ii)' -> ['322i', '322ii']; '150a' -> ['150a']; '450 (vi)' -> ['450vi']."""
    compact = token.replace(" ", "")
    match = INS_PARTS.match(compact)
    if not match:
        return [re.sub(r"[()]", "", compact)]
    base, first, rest = match.groups()
    subs = re.findall(r"[ivx]+", (first or "") + rest)
    return [base + s for s in subs] if subs else [base]


def split_sections(lines: List[str]) -> tuple[List[str], List[str]]:
    """(tables of Part IV, Annexure-1 group lists). Everything before Part IV (category
    descriptions that contain stray numbers) and after Annexure-1 is ignored."""
    part_iv = next(i for i, ln in enumerate(lines) if ln.strip().startswith("IV. USE OF FOOD ADDITIVES"))
    annex = next(i for i, ln in enumerate(lines) if ln.strip().startswith("Annexure-1"))
    end = next((i for i, ln in enumerate(lines) if i > annex and ln.strip().startswith("ANNEX TO GMP")), len(lines))
    return lines[part_iv:annex], lines[annex:end]


def extract_ins(table_lines: Iterable[str], annex_lines: Iterable[str]) -> Set[str]:
    found: Set[str] = set()
    for line in table_lines:
        for match in TABLE_ROW.finditer(line):
            found.update(expand_ins(match.group(1)))
    for line in annex_lines:
        if line.startswith(("Group", "=====")):
            continue
        match = ANNEX_ROW.search(line)
        if match:
            found.update(expand_ins(match.group(1)))
    return found


def read_pdf_lines(path: Path) -> List[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required for this one-time step: see the module docstring.")
    return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages).split("\n")


def main():
    tables, annex = split_sections(read_pdf_lines(PDF_PATH))
    codes = sorted(extract_ins(tables, annex))
    payload = {
        "source": "FSSAI Food Products Standards and Food Additives Regulations, 2011, Appendix A, Version 3 (01.08.2025)",
        "note": "Positive list only: additives named in the permitted-use tables. Absence means 'not extracted', never 'not permitted'.",
        "ins_codes": codes,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(codes)} INS codes to {OUT_PATH}")


if __name__ == "__main__":
    main()
