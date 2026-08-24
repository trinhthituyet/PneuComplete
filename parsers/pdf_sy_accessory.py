"""Trích BẢNG TRA phụ kiện manifold SY (gasket, end plate) từ PDF → bảng `part`.

Khác với ngữ pháp mã hàng: các phụ kiện này KHÔNG ghép từ ô mà tra theo
(series, kiểu manifold) → mã hàng. Ví dụ trang 73:

    Type 20, 23, 20SA, 23SA <Standard>        Type 20P, 23P <Standard>
    SY3000 → SY3000-26-9A                     SY3000 → SY3000-26-10A
    SY5000 → SY5000-26-20A   ← mã BOM dùng    SY5000 → SY5000-26-21A
    SY7000 → SY7000-26-22A                    SY7000 → SY7000-26-23A

Gasket đơn giản hơn: SY□000-GS-1 theo series (trang 45, 51).

Vì vậy lưu thành `part` + attrs, rồi luật dùng `from_parts` để tra — cùng cơ chế
đã dùng cho mã van quét từ catalog.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db  # noqa: E402

NAME = "pdf_sy_accessory"
VERSION = "1"
PDF = db.ROOT / "DOCUMENT" / "MAINFOLD" / "7-1-2-p0723-0963-SY3000_en.pdf"

# (mã, series, vai trò, kiểu manifold, ghi chú) — đọc trực tiếp từ bảng
END_PLATE_PAGE = 73
GASKET_PAGES = (45, 51)


def _text(page):
    return subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(PDF), "-"],
        capture_output=True, text=True, timeout=120).stdout


# Bảng end plate trang 73, ĐỌC TAY. Regex tự động không giữ được cột
# "Type ..." vì -layout trộn 2 bảng cạnh nhau vào cùng dòng; mà kiểu manifold là
# thứ quyết định mã (Type 20 và Type 20P khác end plate), nên không được bỏ.
END_PLATES = [
    # (mã, series, kiểu manifold, chuẩn)
    ("SY3000-26-9A",    "SY3000", "20, 23, 20SA, 23SA", None),
    ("SY5000-26-20A",   "SY5000", "20, 23, 20SA, 23SA", None),   # ← mã BOM dùng
    ("SY7000-26-22A",   "SY7000", "20, 23, 20SA, 23SA", None),
    ("SY9000-26-1A",    "SY9000", "20, 23, 20SA, 23SA", None),
    ("SY3000-26-10A",   "SY3000", "20P, 23P", None),
    ("SY5000-26-21A",   "SY5000", "20P, 23P", None),
    ("SY7000-26-23A",   "SY7000", "20P, 23P", None),
    ("SY9000-26-3A",    "SY9000", "20P, 23P", None),
    ("SY3000-26-19A-Q", "SY3000", "20, 23, 20SA, 23SA", "CE/UKCA"),
    ("SY5000-26-1A-Q",  "SY5000", "20, 23, 20SA, 23SA", "CE/UKCA"),
    ("SY7000-26-1A-Q",  "SY7000", "20, 23, 20SA, 23SA", "CE/UKCA"),
    ("SY9000-26-1A-Q",  "SY9000", "20, 23, 20SA, 23SA", "CE/UKCA"),
    ("SY3000-26-20A-Q", "SY3000", "20P, 23P", "CE/UKCA"),
    ("SY5000-26-3A-Q",  "SY5000", "20P, 23P", "CE/UKCA"),
    ("SY7000-26-3A-Q",  "SY7000", "20P, 23P", "CE/UKCA"),
    ("SY9000-26-3A-Q",  "SY9000", "20P, 23P", "CE/UKCA"),

    # ── Thế hệ SY PLUG-IN mới (SY_M) ────────────────────────────────────────
    # Nguồn: DOCUMENT/MAINFOLD/7-1-2-p0387-0722-SY_en.pdf.
    # BOM máy 24-236 dùng SY50M-26-1A-NA ×4 — máy đó dùng manifold
    # SS5Y5-10SVA-13B-C6A-NA, tức thế hệ plug-in mới, không phải Type 20 cũ.
    #
    # ⚠ CHƯA XÁC ĐỊNH: catalog ghi "SY50M-26-1A(-B)" — hậu tố trong ngoặc là một
    # BIẾN THỂ, còn mã BOM dùng là "-NA". Chưa tìm được bảng giải nghĩa -NA/-B
    # nên KHÔNG khai kiểu manifold (để None) thay vì đoán. Engine vẫn đọc được mã,
    # chỉ chưa tự chọn được giữa các biến thể.
    ("SY30M-26-1A",     "SY3000", None, None),
    ("SY50M-26-1A",     "SY5000", None, None),
    ("SY70M-26-1A",     "SY7000", None, None),
    # -26-2A = blanking plate: bịt chỗ trống trên manifold, dùng khi chừa station
    # để lắp thêm van sau. Khác end plate (bịt hai đầu đế).
    ("SY30M-26-2A",     "SY3000", None, None),
    ("SY50M-26-2A",     "SY5000", None, None),
    ("SY70M-26-2A",     "SY7000", None, None),
]


def scan_end_plates():
    """Đối chiếu bảng đọc tay với text PDF — mã nào không có trong PDF thì báo."""
    txt = _text(END_PLATE_PAGE)
    out = []
    for code, series, mtype, std in END_PLATES:
        out.append({
            "part_number": code, "series_size": series, "role": "end_plate",
            "manifold_type": mtype, "compliance": std, "page": END_PLATE_PAGE,
            "verified_in_pdf": code in txt,
        })
    return out


def scan_gaskets():
    out = []
    for pg in GASKET_PAGES:
        for mm in re.finditer(r"(SY[3579]000)\s+(SY[3579]000-GS-\d)", _text(pg)):
            out.append({"part_number": mm.group(2), "series_size": mm.group(1),
                        "role": "gasket", "manifold_type": None,
                        "compliance": None, "page": pg})
    # gasket của series không nằm cùng dòng với tên series (bảng bị -layout tách)
    for pg in GASKET_PAGES:
        for mm in re.finditer(r"\b(SY([3579])000-GS-\d)\b", _text(pg)):
            out.append({"part_number": mm.group(1), "series_size": f"SY{mm.group(2)}000",
                        "role": "gasket", "manifold_type": None,
                        "compliance": None, "page": pg})
    return out


def load(con):
    if not PDF.exists():
        return {"error": f"không có {PDF}"}
    sid = con.execute("select id from series where catalog_id='SY-5-E'").fetchone()
    if not sid:
        return {"error": "chưa có series SY-5-E"}

    src = con.execute(
        """insert or ignore into source_doc (kind, uri, title) values ('pdf',?,?)""",
        (str(PDF.relative_to(db.ROOT)), "SY3000 catalog p0723-0963"))
    srow = con.execute("select id from source_doc where uri=?",
                       (str(PDF.relative_to(db.ROOT)),)).fetchone()

    rows = scan_end_plates() + scan_gaskets()
    seen, n = set(), 0
    for r in rows:
        pn = r["part_number"]
        if pn in seen:
            continue
        seen.add(pn)
        attrs = {k: v for k, v in r.items() if k != "part_number" and v is not None}
        attrs["_source"] = f"{PDF.name} trang {r['page']}"
        con.execute(
            """insert into part (part_number, series_id, description, attrs, source_id)
               values (?,?,?,?,?)
               on conflict (maker, part_number) do update set
                 attrs=excluded.attrs, description=excluded.description""",
            (pn, sid["id"], f"SY {r['role']} — {r['series_size']}",
             json.dumps(attrs, ensure_ascii=False), srow["id"] if srow else None))
        n += 1
    con.commit()
    return {"loaded": n, "end_plates": sum(1 for r in rows if r["role"] == "end_plate"),
            "gaskets": len({r["part_number"] for r in rows if r["role"] == "gasket"})}


if __name__ == "__main__":
    con = db.connect()
    print(load(con))
    for r in con.execute("""select part_number, json_extract(attrs,'$.role') role,
                            json_extract(attrs,'$.series_size') s,
                            json_extract(attrs,'$.manifold_type') mt
                            from part where json_extract(attrs,'$.role') in
                            ('end_plate','gasket') order by role, part_number"""):
        print(f"  {r['part_number']:22} {r['role']:10} {r['s']:8} {r['mt'] or ''}")
    con.close()
