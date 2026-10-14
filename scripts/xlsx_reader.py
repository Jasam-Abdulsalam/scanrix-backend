"""Minimal .xlsx reader using only the standard library (an .xlsx file is a zip of XML).
Reads values only (no formulas, styles or dates): enough for seed data files."""
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
LETTERS = re.compile(r"[A-Z]+")


def _shared_strings(z: zipfile.ZipFile) -> List[str]:
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{NS}t")) for si in root]


def _cell_value(cell, strings: List[str]) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{NS}t"))
    v = cell.find(f"{NS}v")
    if v is None or v.text is None:
        return ""
    return strings[int(v.text)] if cell.get("t") == "s" else v.text


def read_sheet(path: Path, sheet_file: str = "xl/worksheets/sheet1.xml", header_row: int = 1) -> List[Dict[str, str]]:
    """Rows below `header_row` as {header text: value}. Empty cells are omitted."""
    with zipfile.ZipFile(path) as z:
        strings = _shared_strings(z)
        sheet_data = ET.fromstring(z.read(sheet_file)).find(f"{NS}sheetData")
    headers: Dict[str, str] = {}
    rows: List[Dict[str, str]] = []
    for row in sheet_data:
        values = {LETTERS.match(c.get("r")).group(): _cell_value(c, strings) for c in row}
        values = {k: v for k, v in values.items() if v != ""}
        if int(row.get("r")) == header_row:
            headers = {col: text.strip() for col, text in values.items()}
        elif int(row.get("r")) > header_row and values:
            rows.append({headers[col]: v for col, v in values.items() if col in headers})
    return rows
