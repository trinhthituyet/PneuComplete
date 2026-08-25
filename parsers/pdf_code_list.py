"""Rút `requires` từ BẢNG LIỆT KÊ MÃ HÀNG (khác ma trận ×).

VÌ SAO CẦN BỘ ĐỌC THỨ HAI: parsers/pdf_option_matrix.py đọc bảng "ký hiệu × cỡ
thân" của họ FRL. Họ phụ kiện KQ2 KHÔNG có bảng đó — catalog liệt kê thẳng từng
mã hàng có thật trong bảng kích thước (`KQ2H04-M5…`, `KQ2L06-01…`). Danh sách mã
hiện hữu là nguồn MẠNH HƠN ma trận đánh dấu: nó là cái đang bán, không phải suy
từ ô V/—.

    python3 -m parsers.pdf_code_list            # xem rút được gì, KHÔNG ghi
    python3 -m parsers.pdf_code_list --write    # chạy cổng rồi ghi vào YAML

── BA THỨ CHỈ THẤY KHI ĐO ───────────────────────────────────────────────────
1. PLACEHOLDER: catalog in MỘT dòng cho nhiều biến thể, dùng ký tự vùng-dùng-
   riêng (PUA) thay chỗ vật liệu ren — `KQ2L06-01S`. Lọc bỏ dòng có
   placeholder là mất 'KQ2L06-01' (mã CÓ THẬT trong BOM khách hàng). Nên chỉ đọc
   BA Ô ĐẦU (hình dạng · cỡ ống · cỡ cửa) và bỏ hẳn phần đuôi.
   Và KHÔNG suy nghĩa của placeholder: cùng ký tự , catalog chú giải là
   "A, N" ở trang phụ kiện nhưng "B (Black), R (Red)…" ở trang ống — hai nghĩa
   theo ngữ cảnh, đoán một nghĩa là sai.

2. CỬA CÓ THỂ LÀ ỐNG: 'KQ2U06-08' là đầu nối rút gọn ø6→ø8, nên '08' ở đây là
   cỡ ỐNG THỨ HAI chứ không phải ren. Ngữ pháp đánh dấu bằng hậu tố 'x' ('08x')
   mà mã in ra không có, nên phải thử cả hai dạng.

3. CỠ ỐNG INCH: mã CHẴN là mét (02=ø2, 04=ø4…), mã LẺ là inch (01=ø1/8,
   03=ø5/32, 05=ø3/16, 07=ø1/4, 09=ø5/16, 11=ø3/8, 13=ø1/2). Ngữ pháp DB chỉ
   khai 8 cỡ mét, nên mã inch KHÔNG parse được — 'KQ2H01-32' còn bị đọc SAI
   thành port_size='01'. Chưa sửa (BOM hiện tại 0 dòng inch), nhưng ghi ra đây
   để không ai tưởng bộ đọc bỏ sót.

── CỔNG ─────────────────────────────────────────────────────────────────────
G1 đủ-mã     rút được ≥500 mã, phủ ≥80% hình dạng khai trong ngữ pháp
G2 mã-thật   MỌI mã KQ2 trong BOM khách hàng phải thoả ràng buộc. Nguồn đối
             chiếu ĐỘC LẬP với catalog. Loại một mã có thật = ràng buộc sai.
G3 không-rỗng mỗi ô có ràng buộc còn ≥1 lựa chọn cho mỗi giá trị của ô neo
"""
import collections
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEED = ROOT / "db/seed/grammar"

# Cỡ ống MÉT. Mã lẻ là inch, ngữ pháp chưa khai nên bỏ qua (xem docstring §3).
METRIC_OD = {"02", "04", "06", "08", "10", "12", "16", "23"}

# (tệp YAML, catalog_id, pdf)
SOURCES = [
    ("kq2.yaml", "KQ2-E", "DOCUMENT/FITTING/es50-37-kq2.pdf"),
]

# ── DẠNG THỨ BA: BẢNG KHAI THẲNG "ô neo → các giá trị hợp lệ" ────────────────
# Họ AS…F không có ma trận ×, cũng không liệt kê đủ mã (cả catalog chỉ 5 mã đầy
# đủ — quá thưa, rút ràng buộc từ đó sẽ loại nhầm). Nhưng trang How to Order khai
# THẲNG: thân 1 → M5, 10-32UNF · thân 2 → 1/8, 1/4 · thân 3 → 3/8 · thân 4 → 1/2.
# Đọc bảng đó bằng toạ độ: cột trái là giá trị ô neo, cột phải là các giá trị
# hợp lệ, cùng hàng.
PAIR_SOURCES = [
    {"file": "as1.yaml", "cid": "AS1-E",
     "pdf": "DOCUMENT/SPCL/7-9-3-p0773-0800-AS-F_en.pdf", "page": 7,
     "anchor": "body_size", "dep": "port_size",
     # nhãn in trong bảng → mã trong ngữ pháp. Đối chiếu mã BOM thật:
     # AS1201F-M5-06A (thân 1, cửa M5) · AS2201F-01-06SA (thân 2, cửa 01).
     "label_map": {"M5 x 0.8": "M5", "10-32UNF": "U10/32",
                   "1/8": "01", "1/4": "02", "3/8": "03", "1/2": "04"}},
    {"file": "as.yaml", "cid": "AS-E-E",
     "pdf": "DOCUMENT/SPCL/7-9-3-p0773-0800-AS-F_en.pdf", "page": 7,
     "anchor": "body_size", "dep": "port_size",
     "label_map": {"M5 x 0.8": "M5", "1/8": "01", "1/4": "02",
                   "3/8": "03", "1/2": "04"}},
]


def read_pairs(pdf, page, label_map, anchor_vals, dep_vals):
    """Đọc bảng 'ô neo → giá trị hợp lệ' theo HÀNG. Trả {neo: {giá trị dep}}.

    Ghép theo cy (cùng hàng) chứ không theo thứ tự đọc.

    DUNG SAI THEO CHIỀU CAO Ô, không phải hằng số: ô bảng có thể cao HAI DÒNG.
    Đo được: thân '2' ở cy 259,7 và nhãn '1/8, 1/4' ở 259,8 (lệch 0,1) — nhưng
    thân '1' ở cy 160,4 còn nhãn của nó ở 157,3 ('M5 x 0.8') và 163,6
    ('10-32UNF'), lệch tới 3,2. Dung sai 1,5 bỏ mất ĐÚNG thân 1, mà đó là mã BOM
    khách hàng dùng nhiều nhất (AS1201F-M5-06A ×39).
    Lấy 0,6 × bước dòng đo từ chính trang: đủ trùm ô hai dòng, chưa chạm ô kề.
    """
    from parsers import pdf_chart
    ws = pdf_chart.words(pdf, page)
    ys = sorted({round((wy0 + wy1) / 2, 1) for _, wy0, _, wy1, _ in ws})
    gaps = sorted(b - a for a, b in zip(ys, ys[1:]) if 1.0 < b - a < 30)
    pitch = gaps[len(gaps) // 2] if gaps else 8.0
    tol = 0.6 * pitch * 2                    # ô cao tối đa hai dòng
    out = collections.defaultdict(set)
    for wx0, wy0, wx1, wy1, t in ws:
        v = t.strip()
        if v not in anchor_vals:
            continue
        cy, cx = (wy0 + wy1) / 2, (wx0 + wx1) / 2
        # GHÉP THEO TỪNG DÒNG CON, không gộp cả ô thành một chuỗi. Ô cao hai
        # dòng nên gộp theo cx cho ra 'M5 x 10-32UNF 0.8 …' — hai dòng xen kẽ,
        # và regex 'M5 x 0.8' trượt dù nhãn CÓ trong ô. Nhóm lại theo cy trước.
        sub = collections.defaultdict(list)
        for ux0, uy0, ux1, uy1, u in ws:
            ucy, ucx = (uy0 + uy1) / 2, (ux0 + ux1) / 2
            if abs(ucy - cy) <= tol and ucx > cx:
                sub[round(ucy, 1)].append((ucx, u))
        lines = [" ".join(u for _, u in sorted(v)) for v in sub.values()]
        for lab, code in label_map.items():
            if code in dep_vals and any(re.search(re.escape(lab), l) for l in lines):
                out[v].add(code)
    return out

CODE = re.compile(r"\bKQ2([A-Z]{1,2})(\d{2})-(G0\d|M\d|\d{2}|99|00)")


def read_codes(pdf, opts):
    """Quét toàn catalog, trả (shape→{od}, od→{port}, số mã đọc được)."""
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         capture_output=True, text=True).stdout
    shp = collections.defaultdict(set)
    prt = collections.defaultdict(set)
    n = 0
    for m in CODE.finditer(txt):
        sh, od, po = m.groups()
        if od not in METRIC_OD or sh not in opts.get("shape", ()):
            continue
        hit = [x for x in (po, po + "x") if x in opts.get("port_size", ())]
        if not hit:
            continue
        n += 1
        shp[sh].add(od)
        for x in hit:
            prt[od].add(x)
    return shp, prt, n


def gate(con, cid, shp, prt, n_code, opts):
    from engine import parser as P
    rep, ok = [], True

    n_shape = len(opts.get("shape", ()))
    good = n_code >= 500 and len(shp) >= 0.8 * n_shape
    ok &= good
    rep.append(("G1-đủ-mã", good,
                f"{n_code} mã · {len(shp)}/{n_shape} hình dạng có mã"))

    sid = con.execute("select id from series where catalog_id=?", (cid,)).fetchone()
    sid = sid["id"] if sid else None
    real = [r["raw_code"] for r in con.execute(
        "select distinct raw_code from bom_line where raw_code like ?",
        (cid.split("-")[0] + "%",))]
    bad, n_own = [], 0
    for code in real:
        r = P.parse(con, code)
        if not r.get("ok") or (sid and r.get("series_id") != sid):
            continue
        n_own += 1
        s = r.get("slots") or {}
        sh, od, po = s.get("shape"), s.get("tube_od"), s.get("port_size")
        if sh and od and od not in shp.get(sh, set()):
            bad.append(f"{code}: {sh}×{od}")
        if od and po and po not in prt.get(od, set()):
            bad.append(f"{code}: ống{od}×cửa{po}")
    ok &= not bad
    rep.append(("G2-mã-thật", not bad,
                f"{n_own} mã BOM thật thuộc họ này"
                + ("" if not bad else " · LOẠI NHẦM: " + "; ".join(bad[:3]))))

    empty = [k for k, v in shp.items() if not v] + [k for k, v in prt.items() if not v]
    ok &= not empty
    rep.append(("G3-không-rỗng", not empty,
                f"{len(shp)} hình dạng × {len(prt)} cỡ ống"
                + ("" if not empty else " · RỖNG: " + ", ".join(empty[:3]))))
    return ok, rep


def render(path, shp, prt):
    """Chèn requires vào dòng option: cỡ ống ← hình dạng, cỡ cửa ← cỡ ống."""
    lines = path.read_text().split("\n")
    slot, n_add = None, 0
    out = []
    for ln in lines:
        m = re.match(r"\s*name:\s*(\w+)", ln)
        if m:
            slot = m.group(1)
        mo = re.match(r'(\s*- \{code: "([^"]+)".*?)(\}\s*)$', ln)
        if mo and "requires:" not in ln:
            code = mo.group(2)
            if slot == "tube_od":
                shapes = sorted(k for k, v in shp.items() if code in v)
                if shapes:
                    ln = (mo.group(1) + ", requires: {shape: ["
                          + ", ".join(f'"{s}"' for s in shapes) + "]}" + mo.group(3))
                    n_add += 1
            elif slot == "port_size":
                ods = sorted(k for k, v in prt.items() if code in v)
                if ods:
                    ln = (mo.group(1) + ", requires: {tube_od: ["
                          + ", ".join(f'"{o}"' for o in ods) + "]}" + mo.group(3))
                    n_add += 1
        out.append(ln)
    return "\n".join(out), n_add


def gate_pairs(con, cid, anchor, dep, table):
    """Cổng cho bảng cặp: G2 (mã BOM thật) + G3 (không rỗng)."""
    from engine import parser as P
    sid = con.execute("select id from series where catalog_id=?", (cid,)).fetchone()
    sid = sid["id"] if sid else None
    pre = re.match(r"[A-Z]+", cid).group(0)
    real = [r["raw_code"] for r in con.execute(
        "select distinct raw_code from bom_line where raw_code like ?", (pre + "%",))]
    bad, n_own = [], 0
    for code in real:
        r = P.parse(con, code)
        if not r.get("ok") or (sid and r.get("series_id") != sid):
            continue
        n_own += 1
        s = r.get("slots") or {}
        a, d = s.get(anchor), s.get(dep)
        if a and d and d not in table.get(a, set()):
            bad.append(f"{code}: {anchor}={a} không nhận {dep}={d}")
    empty = [k for k, v in table.items() if not v]
    rep = [("G2-mã-thật", not bad,
            f"{n_own} mã BOM thật thuộc họ này"
            + ("" if not bad else " · LOẠI NHẦM: " + "; ".join(bad[:3]))),
           ("G3-không-rỗng", not empty,
            f"{len(table)} giá trị {anchor}"
            + ("" if not empty else " · RỖNG: " + ", ".join(empty)))]
    return (not bad and not empty), rep


def render_pairs(path, anchor, dep, table):
    """Chèn requires vào ô `dep`: mỗi mã nhận danh sách giá trị `anchor` hợp lệ."""
    lines = path.read_text().split("\n")
    slot, n_add, out = None, 0, []
    for ln in lines:
        m = re.match(r"\s*name:\s*(\w+)", ln)
        if m:
            slot = m.group(1)
        mo = re.match(r'(\s*- \{code: "([^"]+)".*?)(\}\s*)$', ln)
        if mo and slot == dep and "requires:" not in ln:
            keys = sorted(k for k, v in table.items() if mo.group(2) in v)
            if keys:
                ln = (mo.group(1) + f", requires: {{{anchor}: ["
                      + ", ".join(f'"{k}"' for k in keys) + "]}" + mo.group(3))
                n_add += 1
        out.append(ln)
    return "\n".join(out), n_add


def main(argv):
    from crawler import db
    write = "--write" in argv
    con = db.connect()
    for fname, cid, pdf in SOURCES:
        print(f"── {cid} ← {Path(pdf).name}")
        opts = collections.defaultdict(set)
        for r in con.execute(
                """select cs.name slot, o.code from code_option o
                   join code_slot cs on cs.id = o.slot_id
                   join series s on s.id = cs.series_id
                   where s.catalog_id = ?""", (cid,)):
            opts[r["slot"]].add(r["code"])
        shp, prt, n = read_codes(pdf, opts)
        for k in sorted(shp):
            print(f"   {k:3} → cỡ ống {sorted(shp[k])}")
        print("   cỡ ống → cỡ cửa:")
        for k in sorted(prt):
            print(f"     {k} → {sorted(prt[k])}")
        ok, rep = gate(con, cid, shp, prt, n, opts)
        for gid, g, detail in rep:
            print(f"   {'PASS' if g else 'FAIL'}  {gid:14} {detail}")
        if not ok:
            print("   → CHƯA ĐẠT CỔNG: không ghi ràng buộc.")
            return 1
        text, n_add = render(SEED / fname, shp, prt)
        if write:
            (SEED / fname).write_text(text)
            print(f"   ✓ ghi {n_add} ràng buộc vào {fname}")
        else:
            print(f"   (chưa ghi) sẽ thêm {n_add} ràng buộc — thêm --write để ghi")

    for src in PAIR_SOURCES:
        print(f"── {src['cid']} ← {Path(src['pdf']).name} tr{src['page']}")
        opts = collections.defaultdict(set)
        for r in con.execute(
                """select cs.name slot, o.code from code_option o
                   join code_slot cs on cs.id = o.slot_id
                   join series s on s.id = cs.series_id
                   where s.catalog_id = ?""", (src["cid"],)):
            opts[r["slot"]].add(r["code"])
        table = read_pairs(src["pdf"], src["page"], src["label_map"],
                           opts[src["anchor"]], opts[src["dep"]])
        print("   " + " · ".join(f"{k}→{sorted(v)}" for k, v in sorted(table.items())))
        ok, rep = gate_pairs(con, src["cid"], src["anchor"], src["dep"], table)
        for gid, g, detail in rep:
            print(f"   {'PASS' if g else 'FAIL'}  {gid:14} {detail}")
        if not ok:
            print("   → CHƯA ĐẠT CỔNG: không ghi ràng buộc.")
            return 1
        text, n_add = render_pairs(SEED / src["file"], src["anchor"],
                                   src["dep"], table)
        if write:
            (SEED / src["file"]).write_text(text)
            print(f"   ✓ ghi {n_add} ràng buộc vào {src['file']}")
        else:
            print(f"   (chưa ghi) sẽ thêm {n_add} ràng buộc")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
