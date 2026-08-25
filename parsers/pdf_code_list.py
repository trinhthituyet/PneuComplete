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

# (tệp YAML, catalog_id, pdf, ô neo, ô phụ thuộc…)
SOURCES = [
    ("kq2.yaml", "KQ2-E", "DOCUMENT/FITTING/es50-37-kq2.pdf"),
]

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
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
