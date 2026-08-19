"""Parser bảng kích thước trong PDF catalog → spec theo bore.

Lấy các cột mà engine cần cho tính toán và cho giao diện kết nối:
    D   đường kính cần        → tính lực kéo
    MM  ren đầu cần           → giao diện rod_end
    P   cỡ ren cửa khí        → giao diện air_port

Vì sao cần parser này: bản đầu tôi hardcode `{20:8, 25:10, 32:12, 40:14}` trong
engine/calc.py. Nó đúng cho CM2 nhưng SAI ÂM THẦM cho mọi series khác — CJ2, CQ2,
MGP đều có đường kính cần khác. Người dùng chỉ ra: "sẽ có các trường hợp ngoại lệ,
hãy đọc catalog" (mục A3-1). Nên số liệu phải đi theo từng series, đọc từ catalog.

Cách map cột: KHÔNG đếm theo thứ tự ô (bảng có rowspan, số ô mỗi dòng không đều),
mà lấy toạ độ x của header rồi khớp ô dữ liệu theo x gần nhất — cùng kỹ thuật đã
dùng cho sơ đồ How-to-Order.

Đối chiếu chéo: một PDF có nhiều bảng kích thước (CM2 có 12). Parser đọc HẾT rồi so
nhau. Lệch nhau → không ghi, đẩy vào review_item. Nhất quán → độ tin cậy cao.
"""
import re
from collections import defaultdict

from parsers import pdf_how_to_order as H

NAME = "pdf_dim_table"
VERSION = "1"

X_TOL = 4.0          # ô dữ liệu lệch header tối đa
BORE_X = (38.0, 54.0)  # cột bore nằm sát lề trái


def _rows(ws):
    r = {}
    for x, y, _, _, t in ws:
        if t.strip():
            r.setdefault(round(y / 2.0), []).append((x, t.strip()))
    return r


def _find_header(rows):
    """Dòng header phải có đủ 'Bore', 'D', 'MM' — dấu hiệu bảng kích thước."""
    for k, cells in sorted(rows.items()):
        toks = [t for _, t in cells]
        if "Bore" in toks and "D" in toks and "MM" in toks:
            return k, sorted(cells)
    return None, None


def parse_page(pdf_path, page):
    ws = H.words(pdf_path, page)
    rows = _rows(ws)
    hy, hdr = _find_header(rows)
    if hy is None:
        return None
    xs, right = {}, {}
    for i, (x, t) in enumerate(hdr):
        if t in ("D", "MM", "P") and t not in xs:
            xs[t] = x
            # biên phải = x của header kế tiếp. Không chặn thì ô MM (x=288) hút
            # luôn giá trị cột NA (x=311) và ra 'M8x1.2524' thay vì 'M8x1.25'.
            nxt = next((hx for hx, _ in hdr[i + 1:] if hx > x + 2), x + 20)
            right[t] = min(nxt - 2, x + 20)
    if "D" not in xs:
        return None

    out = {}
    for k, cells in sorted(rows.items()):
        if k <= hy:
            continue
        cs = sorted(cells)
        bore = next((t for x, t in cs
                     if BORE_X[0] < x < BORE_X[1] and re.fullmatch(r"\d{1,3}", t)), None)
        if not bore:
            continue
        rec = {}
        d = next((t for x, t in cs if abs(x - xs["D"]) <= X_TOL), None)
        if d and re.fullmatch(r"\d+(\.\d+)?", d):
            rec["rod_dia_mm"] = float(d)
        if "MM" in xs:
            mm = [t for x, t in cs if xs["MM"] - X_TOL <= x <= right["MM"]]
            joined = "".join(mm)
            m = re.match(r"(M\d+)x?([\d.]+)?", joined)
            if m:
                rec["rod_end_thread"] = m.group(1) + (f"x{m.group(2)}" if m.group(2) else "")
        if "P" in xs:
            p = next((t for x, t in cs if abs(x - xs["P"]) <= X_TOL), None)
            if p and re.fullmatch(r"\d+/\d+|M\d+", p):
                rec["port_size"] = p
        if rec.get("rod_dia_mm"):
            out.setdefault(int(bore), rec)
    return out or None


def parse(pdf_path, pages=None):
    """Đọc mọi bảng kích thước, đối chiếu chéo. Trả (nhất_quán, xung_đột)."""
    if pages is None:
        import subprocess
        txt = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                             capture_output=True, text=True, timeout=300).stdout
        pages = [i for i, pg in enumerate(txt.split("\f"), 1)
                 if re.search(r"Bore\s+size", pg) and re.search(r"\bMM\b", pg)]

    seen = defaultdict(lambda: defaultdict(set))     # bore → field → {giá trị}
    src = defaultdict(list)
    for pg in pages:
        try:
            got = parse_page(pdf_path, pg)
        except Exception:
            continue
        if not got:
            continue
        for bore, rec in got.items():
            for k, v in rec.items():
                seen[bore][k].add(v)
            src[bore].append(pg)

    agreed, conflict = {}, {}
    for bore, fields in seen.items():
        for k, vals in fields.items():
            if len(vals) == 1:
                agreed.setdefault(bore, {})[k] = next(iter(vals))
            else:
                conflict.setdefault(bore, {})[k] = sorted(vals)
    return {"agreed": agreed, "conflict": conflict,
            "pages": {b: sorted(set(p)) for b, p in src.items()}}


def load(con, run_id, res, series_id, source_page=None):
    """Ghi rod_dia_mm / rod_end_thread / port_size vào attrs của option ô bore.

    Nhờ vậy engine/parser.py tự gộp vào attrs khi parse mã, và calc.py không cần
    bảng hardcode nào nữa.
    """
    import json

    from crawler import db as _db

    slot = con.execute(
        "select id from code_slot where series_id=? and name='bore'", (series_id,)
    ).fetchone()
    if not slot:
        return {"error": "series chưa có ô bore trong ngữ pháp"}

    n = 0
    for bore, rec in (res["agreed"] or {}).items():
        row = con.execute("select id, attrs from code_option where slot_id=? and code=?",
                          (slot["id"], str(bore))).fetchone()
        if not row:
            continue
        attrs = json.loads(row["attrs"] or "{}")
        attrs.update(rec)
        attrs["_source"] = f"bảng kích thước, trang {res['pages'].get(bore)}"
        con.execute("update code_option set attrs=? where id=?",
                    (json.dumps(attrs, ensure_ascii=False), row["id"]))
        n += 1

    for bore, fields in (res["conflict"] or {}).items():
        _db.add_review(con, run_id, "code_option",
                       {"series_id": series_id, "slot_hint": "bore", "bore": bore,
                        "conflict": fields, "pages": res["pages"].get(bore)},
                       confidence=0.3,
                       note="các bảng kích thước trong cùng PDF cho giá trị KHÁC NHAU "
                            "— cần người xác định dùng giá trị nào")
    con.commit()
    return {"updated": n, "conflicts": len(res["conflict"] or {})}
