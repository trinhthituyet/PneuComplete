"""Sinh `requires` cho ngữ pháp FRL từ bảng How-to-Order — CHỈ KHI ĐẠT CỔNG.

    python3 -m parsers.grammar_requires            # xem sẽ ghi gì, KHÔNG ghi
    python3 -m parsers.grammar_requires --write    # chạy cổng rồi ghi vào YAML

VÌ SAO: `requires` phủ 26/483 tuỳ chọn (5%) và họ FRL bằng 0, nên engine sinh mã
KHÔNG TỒN TẠI mà im lặng. Đo được ba mã bịa engine đang sinh:

    AC20-10-D   cửa Rc1 trên thân 20   — bảng ghi '—'
    AC60-06-D   cửa 3/4 trên thân 60   — bảng ghi '—'
    AC25-02-D   cỡ 25                  — catalog -D KHÔNG có AC25

Thiếu một dòng thì người ta thấy; một mã sai thì người ta đặt hàng. Đây là rủi ro
ĐÚNG/SAI, nặng hơn rủi ro THIẾU.

── CỔNG (bốn phần, phải đạt hết) ────────────────────────────────────────────
G1 khớp-ô     mỗi ô chỉ nhận ma trận khi tập ký hiệu khớp TUYỆT ĐỐI (Jaccard
              = 1.0) với tuỳ chọn trong DB. Khớp một phần nghĩa là bảng và ngữ
              pháp nói về hai thứ khác nhau — ghi vào là ràng buộc bịa.
G2 mã-thật    mọi mã FRL trong BOM khách hàng phải VẪN parse được sau khi áp
              ràng buộc. Ràng buộc nào loại một mã CÓ THẬT là ràng buộc sai.
              Đây là nguồn đối chiếu ĐỘC LẬP với PDF.
G3 không-rỗng mỗi ô có ràng buộc phải còn ≥1 tổ hợp hợp lệ cho MỖI cỡ thân —
              ràng buộc làm một cỡ không đặt được gì là đọc sai bảng.
G4 chặn-được  ba mã bịa đo được ở trên phải bị TỪ CHỐI sau khi áp.
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parsers import pdf_option_matrix as OM       # noqa: E402

SEED = ROOT / "db/seed/grammar"

# Họ nào lấy ma trận từ trang nào. Mỗi mục: (tệp YAML, catalog_id, pdf, trang).
SOURCES = [
    ("ac-d.yaml", "AC-D-E", "DOCUMENT/FRL/es40-69-AC-D.pdf", 20),
    ("ar.yaml", "AR-D-E", "DOCUMENT/FRL/es40-69-AC-D.pdf", 100),
]

# Họ FRL có ngữ pháp nhưng KHÔNG rút được ràng buộc, kèm lý do — để lần sau khỏi
# dò lại, và để không ai tưởng là bỏ sót.
NO_MATRIX = {
    "AR10-A-E": "chỉ MỘT cỡ thân (AR10) nên bảng How to Order không có cột cỡ — "
                "không có ràng buộc theo cỡ để rút",
    "AC-A-E": "ngữ pháp khai cỡ 10..40 nhưng DOCUMENT/ chỉ có ES40-60-AC10-A.pdf "
              "(riêng AC10). Thiếu catalog cho cỡ 20..40 của thế hệ -A",
    "AMC-E": "chưa có catalog AMC trong DOCUMENT/",
}

# Mã bịa engine ĐANG sinh — cổng G4 đòi chặn được đúng những mã này.
MUST_REJECT = [
    ("AC-D-E", {"size": "20", "port_size": "1"}, "cửa Rc1 trên thân 20"),
    ("AC-D-E", {"size": "60", "port_size": "3/4"}, "cửa 3/4 trên thân 60"),
]


def matrix_for(cid, pdf, page, con):
    """Đọc ma trận + gán ô. Trả {ô: {mã: [cỡ…]}} CHỈ cho ô khớp tuyệt đối."""
    opts = collections.defaultdict(set)
    for r in con.execute(
            """select cs.name slot, o.code from code_option o
               join code_slot cs on cs.id = o.slot_id
               join series s on s.id = cs.series_id where s.catalog_id = ?""", (cid,)):
        opts[r["slot"]].add(r["code"])
    groups, err = OM.read_matrix(pdf, page, opts.get("size", set()))
    if err:
        return None, err, {}
    mapped = OM.map_groups(groups, dict(opts))
    out, skipped = {}, {}
    for slot, (gi, score) in sorted(mapped.items()):
        if slot == "size":
            continue
        if score < 1.0:
            # G1: khớp một phần thì BỎ. Bảng và ngữ pháp đang nói về hai tập khác
            # nhau — ghi vào là ràng buộc bịa, đúng thứ đang cần diệt.
            skipped[slot] = score
            continue
        out[slot] = {sym: sorted((s for s, ok in marks.items() if ok), key=int)
                     for sym, marks in groups[gi]}
    return out, None, skipped


def dead_sizes(con, cid, table):
    """Cỡ thân nào KHÔNG được ma trận nhắc tới — cỡ có trong DB nhưng không có
    trong catalog. Đo được: AC25 nằm trong ngữ pháp nhưng catalog -D không có."""
    live = {s for m in table.values() for szs in m.values() for s in szs}
    have = {r["code"] for r in con.execute(
        """select o.code from code_option o join code_slot cs on cs.id = o.slot_id
           join series s on s.id = cs.series_id
           where s.catalog_id = ? and cs.name = 'size'""", (cid,))}
    return sorted(have - live, key=int)


def render(path, table, dead):
    """Chèn `requires: {size: [...]}` vào từng dòng option của YAML.

    Sửa TẠI CHỖ theo từng dòng thay vì ghi lại cả tệp: mỗi tệp ngữ pháp có phần
    đầu giải thích nguồn và cách đọc, viết tay — ghi đè là mất.
    """
    src = path.read_text()
    lines = src.split("\n")
    slot, n_add, n_dead = None, 0, 0
    out = []
    for ln in lines:
        m = re.match(r"\s*name:\s*(\w+)", ln)
        if m:
            slot = m.group(1)
        mo = re.match(r'(\s*- \{code: "([^"]+)".*?)(\}\s*)$', ln)
        if mo and slot in table and mo.group(2) in table[slot]:
            szs = table[slot][mo.group(2)]
            if f"requires:" not in ln:
                ln = (mo.group(1) + ", requires: {size: ["
                      + ", ".join(f'"{s}"' for s in szs) + "]}" + mo.group(3))
                n_add += 1
        if mo and slot == "size" and mo.group(2) in dead:
            ln = ln.rstrip() + "   # ← KHÔNG có trong catalog, xem grammar_requires"
            n_dead += 1
        out.append(ln)
    return "\n".join(out), n_add, n_dead


def gate(con, cid, table):
    """G2 + G3 + G4. Trả (đạt, [dòng báo cáo])."""
    from engine import parser as P
    rep, ok = [], True

    # G2: mã FRL THẬT trong BOM phải vẫn hợp lệ.
    # LỌC THEO SERIES PARSE RA, không theo tiền tố mã. 'AR10-M5BG-N-A' bắt đầu
    # bằng 'AR' nhưng thuộc ngữ pháp AR10-A-E (có ô exhaust/knob, cỡ 10) — đem
    # so với bảng của AR-D-E là so hai họ khác nhau, và G2 báo "loại nhầm" oan.
    sid = con.execute("select id from series where catalog_id=?", (cid,)).fetchone()
    sid = sid["id"] if sid else None
    real = [r["raw_code"] for r in con.execute(
        """select distinct raw_code from bom_line
           where raw_code like ? order by raw_code""", (cid.split("-")[0] + "%",))]
    bad, n_own = [], 0
    for code in real:
        r = P.parse(con, code)
        if not r.get("ok") or (sid and r.get("series_id") != sid):
            continue                      # mã của họ khác, hoặc vốn không parse được
        n_own += 1
        slots = r.get("slots") or {}
        sz = slots.get("size")
        for slot, m in table.items():
            v = slots.get(slot)
            if v is not None and sz and v in m and sz not in m[v]:
                bad.append(f"{code}: {slot}={v} nhưng bảng nói chỉ có ở {m[v]}")
    ok &= not bad
    rep.append(("G2-mã-thật", not bad,
                f"{n_own}/{len(real)} mã BOM thật thuộc ĐÚNG họ này" +
                ("" if not bad else " · LOẠI NHẦM: " + "; ".join(bad[:2]))))

    # G3: mỗi cỡ còn ít nhất một tuỳ chọn ở mỗi ô có ràng buộc
    live = sorted({s for m in table.values() for szs in m.values() for s in szs},
                  key=int)
    empty = [f"{slot}@{sz}" for slot, m in table.items() for sz in live
             if not any(sz in szs for szs in m.values())]
    ok &= not empty
    rep.append(("G3-không-rỗng", not empty,
                f"{len(table)} ô × {len(live)} cỡ" +
                ("" if not empty else " · RỖNG: " + ", ".join(empty[:3]))))

    # G4: đúng những mã bịa ĐANG sinh phải bị chặn. Không có phần này thì cổng
    # chỉ chứng minh "không phá gì", chưa chứng minh "sửa được gì".
    LBL = {"1/8": "01", "1/4": "02", "3/8": "03", "1/2": "04", "3/4": "06", "1": "10"}
    miss = []
    for c, want, tag in MUST_REJECT:
        if c != cid:
            continue
        sz = want["size"]
        code = LBL.get(want.get("port_size"), want.get("port_size"))
        allowed = table.get("port_size", {}).get(code)
        if allowed is None or sz in allowed:
            miss.append(tag)
    ok &= not miss
    rep.append(("G4-chặn-được", not miss,
                f"{sum(1 for c, *_ in MUST_REJECT if c == cid)} mã bịa đo được"
                + ("" if not miss else " · VẪN LỌT: " + "; ".join(miss))))
    return ok, rep


def main(argv):
    from crawler import db
    write = "--write" in argv
    con = db.connect()
    total_add = 0
    for cid, why in sorted(NO_MATRIX.items()):
        print(f"── {cid:10} BỎ QUA: {why}")
    for fname, cid, pdf, page in SOURCES:
        print(f"── {cid} ← {Path(pdf).name} tr{page}")
        table, err, skipped = matrix_for(cid, pdf, page, con)
        if err:
            print(f"   ✗ {err}")
            return 1
        for slot, m in sorted(table.items()):
            print(f"   {slot:16} " + " · ".join(f"{k}→{','.join(v)}"
                                                for k, v in sorted(m.items())))
        n_slot = len(table) + len(skipped)
        print(f"   PASS  G1-khớp-ô       {len(table)}/{n_slot} ô khớp TUYỆT ĐỐI "
              f"tập ký hiệu với ngữ pháp DB")
        if skipped:
            print("   BỎ (khớp chưa tuyệt đối, không ghi): "
                  + ", ".join(f"{s}={sc}" for s, sc in sorted(skipped.items())))
        dead = dead_sizes(con, cid, table)
        if dead:
            print(f"   ⚠ cỡ có trong ngữ pháp nhưng KHÔNG có trong catalog: {dead}")

        ok, rep = gate(con, cid, table)
        for gid, good, detail in rep:
            print(f"   {'PASS' if good else 'FAIL'}  {gid:14} {detail}")
        if not ok:
            print("   → CHƯA ĐẠT CỔNG: không ghi ràng buộc.")
            return 1

        text, n_add, n_dead = render(SEED / fname, table, set(dead))
        total_add += n_add
        if write:
            (SEED / fname).write_text(text)
            print(f"   ✓ ghi {n_add} ràng buộc vào {fname}"
                  + (f", đánh dấu {n_dead} cỡ không có thật" if n_dead else ""))
        else:
            print(f"   (chưa ghi) sẽ thêm {n_add} ràng buộc"
                  + (f", đánh dấu {n_dead} cỡ không có thật" if n_dead else ""))
    con.close()
    if not write:
        print("\n  thêm --write để ghi, rồi chạy: python3 -m crawler.grammar_seed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
