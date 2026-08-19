"""Đọc .xlsx bằng stdlib (zipfile + xml) — không cần openpyxl/pandas.

Môi trường này không cài được openpyxl (PyPI bị chặn), mà .xlsx vốn chỉ là ZIP
chứa XML nên đọc thẳng. Chỉ hỗ trợ những gì BOM cần: ô text, số, và shared string.
Bỏ qua công thức (lấy giá trị đã tính sẵn trong <v>).
"""
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col_index(ref: str) -> int:
    """'BC12' → 54 (0-based)."""
    letters = re.match(r"([A-Z]+)", ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def sheet_names(path):
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        return [s.get("name") for s in wb.findall(".//m:sheets/m:sheet", NS)]


def read(path, sheet=0):
    """Trả list[list[str]] — lưới ô đã điền, chuỗi rỗng cho ô trống."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))

        names = [n for n in z.namelist()
                 if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        if isinstance(sheet, str):
            idx = sheet_names(path).index(sheet)
        else:
            idx = sheet
        root = ET.fromstring(z.read(names[idx]))

    rows = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        cells = {}
        for c in row.findall("m:c", NS):
            ref, typ = c.get("r"), c.get("t")
            v = c.find("m:v", NS)
            if typ == "s" and v is not None:
                val = shared[int(v.text)]
            elif typ == "inlineStr":
                is_ = c.find("m:is", NS)
                val = "".join(t.text or "" for t in is_.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")) if is_ is not None else ""
            else:
                val = v.text if v is not None else ""
            cells[_col_index(ref)] = (val or "").strip()
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
        else:
            rows.append([])
    return rows
