"""Golden test: so BOM engine SINH RA với BOM bạn ĐÃ MUA, đếm theo từng dòng.

    python3 -m ingest.golden                 # chạy tất cả máy
    python3 -m ingest.golden --machine 23    # lọc theo số máy

Cách so:
  1. Lấy danh sách ACTUATOR từ BOM thật làm INPUT cho engine (giống lúc thiết kế:
     kỹ sư chọn xy-lanh trước, phần còn lại suy ra).
  2. Cấu hình dự án suy từ chính BOM thật (cỡ ống, cỡ van, kiểu manifold…) — vì
     đó là những thứ engine KHÔNG suy được và người dùng phải khai.
  3. So từng dòng: ĐÚNG (mã trùng) · THIẾU (BOM có, engine không đề xuất) ·
     THỪA (engine đề xuất, BOM không có) · LỆCH SỐ LƯỢNG.

Không so những họ engine chưa có ngữ pháp — chúng nằm ở mục "ngoài phạm vi" để
con số ĐÚNG/THIẾU phản ánh chất lượng suy luận, không lẫn với độ phủ dữ liệu.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db          # noqa: E402
from engine import bom, learn          # noqa: E402
from engine import parser as P  # noqa: E402

# Họ CẦN thông tin theo TỪNG xy-lanh mà BOM KHÔNG ghi lại — không thể đo công bằng.
# Van là ví dụ: BOM có 5 van single + 2 double + 4 3-position, nhưng không ghi van
# nào của xy-lanh nào. Engine cần `valve_function` cho từng xy-lanh mới sinh đúng,
# nên tính THIẾU ở đây là oan cho engine, mà tính ĐÚNG cũng là tự phong.
UNDETERMINABLE = [
    (r"^SY[3579]\d{3}-", "van (cần biết chức năng từng cơ cấu, BOM không ghi)"),
]

# Họ mà engine CÓ luật sinh ra. Ngoài danh sách này thì không tính THIẾU/THỪA
# vì đó là thiếu luật, không phải suy luận sai.
IN_SCOPE = [
    (r"^AS[12]\d{3}F",   "speed controller"),
    (r"^D-M9",           "auto switch"),
    (r"^TU\d{4}",        "ống"),
    (r"^SY[3579]\d{3}-", "van"),
    (r"^SY[3579]000-GS", "gasket"),
    (r"^SY[3579]000-26", "end plate"),
    (r"^AC\d{2}",        "FRL"),
    (r"^JA\d{2}-",       "floating joint"),
]

ACTUATOR = re.compile(r"^(CDM2|CM2|MGP|CDQS|CQS|CDG1|CG1|MY1|CDJ2|CJ2)", re.I)


def in_scope(code):
    for pat, name in IN_SCOPE:
        if re.match(pat, code, re.I):
            return name
    return None


def undeterminable(code):
    for pat, name in UNDETERMINABLE:
        if re.match(pat, code, re.I):
            return name
    return None


def real_bom(con, machine_id):
    rows = con.execute(
        """select raw_code, qty, layer, raw_desc from bom_line
           where machine_id=? and raw_desc like '%SMC%'""", (machine_id,)).fetchall()
    return [dict(r) for r in rows]


def guess_project(con, lines):
    """Suy cấu hình dự án TỪ CHÍNH BOM thật.

    Đây là những thứ engine không suy được (A3-5): cỡ ống, cỡ van, kiểu manifold,
    tổng mét ống. Lấy từ BOM thật để phép so là công bằng — ta đang kiểm khả năng
    SUY LUẬN của engine, không kiểm khả năng đọc ý người thiết kế.
    """
    cfg = {}
    for l in lines:
        c = l["raw_code"].upper()
        m = re.match(r"^TU(\d{2})(\d{2})([A-Z]+\d?)-(\d+)$", c)
        if m:
            cfg.setdefault("tube_od_mm", float(m.group(1)))
            cfg.setdefault("tube_color", m.group(3))          # màu là lựa chọn của bạn
            cfg.setdefault("tube_roll_length_m", float(m.group(4)))
        m = re.match(r"^SY([3579])\d{3}-", c)
        if m:
            cfg.setdefault("valve_series_size", f"SY{m.group(1)}000")
            a = P.parse(con, c).get("attrs") or {}
            if a.get("mounting"):
                cfg.setdefault("valve_mounting", a["mounting"])
        if re.match(r"^SS5Y", c):
            cfg.setdefault("use_manifold", True)   # BOM có đế manifold
        if re.match(r"^SY[3579]000-26", c):
            a = P.parse(con, c).get("attrs") or {}
            row = con.execute("select attrs from part where part_number=?", (c,)).fetchone()
            if row:
                import json
                mt = json.loads(row["attrs"]).get("manifold_type")
                if mt:
                    cfg.setdefault("manifold_type", mt)
        m = re.match(r"^AC(\d{2})", c)
        if m:
            cfg.setdefault("frl_size", m.group(1))
            a = P.parse(con, c).get("attrs") or {}
            if a.get("port_size"):
                cfg.setdefault("main_line_port_size", a["port_size"])
            # thế hệ AC (-A hay -D) là lựa chọn của bạn, engine không suy được
            cfg.setdefault("frl_series", "AC-D-E" if c.endswith("-D") else "AC-A-E")
            for k in ("has_lubricator", "has_mist_separator"):
                if k in a:
                    cfg.setdefault(f"frl_{k.replace('has_','')}", a[k])
            if a.get("gauge"):
                cfg.setdefault("frl_gauge", a["gauge"])
            if a.get("auto_drain"):
                cfg.setdefault("frl_auto_drain", a["auto_drain"])
            if a.get("entry"):
                cfg.setdefault("frl_gauge_entry", a["entry"])
            if a.get("output"):
                cfg.setdefault("frl_gauge_output", a["output"])
            if a.get("relief_valve"):
                cfg.setdefault("frl_relief_valve", a["relief_valve"])
    # Tổng mét ống tính RIÊNG cho đường kính mà engine sẽ đề xuất (nhánh xy-lanh).
    # Cộng tất cả mọi cỡ là không công bằng: BOM 23-432 có TU0604B-200 (nhánh ø6)
    # và TU1065B-100 (trục chính ø10) — engine chưa có luật cho đường trục chính
    # nên nếu cộng cả 100 m ø10 vào thì engine đề xuất thừa cuộn ø6.
    by_od = {}
    for l in lines:
        m = re.match(r"^TU(\d{2})\d{2}\w*-(\d+)$", l["raw_code"].upper())
        if m:
            od = float(m.group(1))
            by_od[od] = by_od.get(od, 0.0) + float(m.group(2)) * (l["qty"] or 1)
    if by_od:
        want_od = cfg.get("tube_od_mm") or min(by_od)
        cfg["tube_total_m"] = by_od.get(want_od, sum(by_od.values()))
        cfg["_tube_m_by_od"] = by_od
    return cfg


def compare(con, machine):
    lines = real_bom(con, machine["id"])
    inputs = [(l["raw_code"], l["qty"] or 1) for l in lines
              if ACTUATOR.match(l["raw_code"]) and P.parse(con, l["raw_code"]).get("ok")]
    # gộp trùng: cùng mã xuất hiện ở nhiều sheet thì cộng số lượng
    agg = Counter()
    for c, n in inputs:
        agg[c] += n
    inputs = [(c, n) for c, n in agg.items()]
    if not inputs:
        return None

    cfg = guess_project(con, lines)
    dbg = cfg.pop("_tube_m_by_od", None)

    # BỎ RA MỘT MÁY (leave-one-out). Chốt chống tự lừa quan trọng nhất của phép đo:
    # tri thức trong engine/learn.py phải học từ các máy KHÁC máy đang chấm. Học
    # từ chính máy đang chấm rồi báo điểm cao là đưa trước đáp án cho bài thi.
    #
    # Lưu ý cfg vẫn lấy TỪ máy đang chấm — nhưng chỉ những khoá RIÊNG MÁY mà engine
    # về nguyên tắc không suy được (tổng mét ống, cỡ van, kiểu manifold). Đó là để
    # phép so công bằng, ta đang kiểm khả năng SUY LUẬN. Còn các khoá THÓI QUEN thì
    # phải đến từ máy khác, nếu không thì không đo được nó có CHUYỂN sang máy mới
    # được hay không.
    for k in learn.HABIT_KEYS:
        cfg.pop(k, None)

    res = bom.build(con, inputs, cfg, project_name=f"golden:{machine['name'][:30]}",
                    learn_exclude=[machine["id"]])

    # gộp theo mã
    got = Counter()
    for l in res["lines"]:
        if l["layer"] != "actuator" or not ACTUATOR.match(l["part_number"]):
            got[l["part_number"].upper()] += l["qty"]
    want = Counter()
    for l in lines:
        c = l["raw_code"].upper()
        if ACTUATOR.match(c):
            continue
        want[c] += l["qty"] or 0

    undet = {c: n for c, n in want.items() if undeterminable(c)}
    scope_want = {c: n for c, n in want.items()
                  if in_scope(c) and not undeterminable(c)}
    scope_got = {c: n for c, n in got.items()
                 if in_scope(c) and not undeterminable(c)}

    exact = {c: (scope_got[c], scope_want[c]) for c in scope_got if c in scope_want}
    right_qty = {c: v for c, v in exact.items() if v[0] == v[1]}
    wrong_qty = {c: v for c, v in exact.items() if v[0] != v[1]}
    missing = {c: n for c, n in scope_want.items() if c not in scope_got}
    extra = {c: n for c, n in scope_got.items() if c not in scope_want}
    out_of_scope = {c: n for c, n in want.items() if not in_scope(c)}

    return {"machine": machine, "inputs": inputs, "cfg": cfg, "res": res,
            "right_qty": right_qty, "wrong_qty": wrong_qty,
            "missing": missing, "extra": extra, "out_of_scope": out_of_scope,
            "undeterminable": undet}


def show(r):
    m = r["machine"]
    print("═" * 84)
    print(f"GOLDEN TEST · {m['name'][:50]}")
    print(f"  {m['notes']}")
    print("═" * 84)
    print(f"  INPUT ({len(r['inputs'])} loại actuator lấy từ BOM thật):")
    for c, n in r["inputs"]:
        print(f"      {c:24} ×{n}")
    print(f"  CẤU HÌNH suy từ BOM thật: "
          + ", ".join(f"{k}={v}" for k, v in sorted(r["cfg"].items())))

    n_ok, n_q, n_m, n_e = (len(r["right_qty"]), len(r["wrong_qty"]),
                           len(r["missing"]), len(r["extra"]))
    tot = n_ok + n_q + n_m + n_e

    print(f"\n  ✓ ĐÚNG cả mã và số lượng   {n_ok}")
    for c, (g, w) in sorted(r["right_qty"].items()):
        print(f"      {c:24} ×{g}")
    if r["wrong_qty"]:
        print(f"\n  ≈ ĐÚNG mã, LỆCH số lượng    {n_q}")
        for c, (g, w) in sorted(r["wrong_qty"].items()):
            print(f"      {c:24} engine ×{g}  ·  BOM ×{w}")
    if r["missing"]:
        print(f"\n  ✗ THIẾU (BOM có, engine không đề xuất)   {n_m}")
        for c, w in sorted(r["missing"].items()):
            print(f"      {c:24} ×{w}   [{in_scope(c)}]")
    if r["extra"]:
        print(f"\n  ! THỪA (engine đề xuất, BOM không có)    {n_e}")
        for c, g in sorted(r["extra"].items()):
            print(f"      {c:24} ×{g}   [{in_scope(c)}]")
    if r["undeterminable"]:
        print(f"\n  ~ KHÔNG ĐO ĐƯỢC ({len(r['undeterminable'])} mã) — cần thông tin "
              f"theo từng xy-lanh mà BOM không ghi lại:")
        for c, n in sorted(r["undeterminable"].items()):
            print(f"      {c:24} ×{n}   [{undeterminable(c)}]")
    if r["out_of_scope"]:
        print(f"\n  — NGOÀI PHẠM VI (engine chưa có luật sinh): "
              f"{len(r['out_of_scope'])} mã")
        print("      " + ", ".join(sorted(r["out_of_scope"])[:12]))

    if tot:
        print(f"\n  ĐIỂM: {n_ok}/{tot} dòng đúng hoàn toàn = {n_ok/tot*100:.0f}%")
    print(f"  Engine còn báo {len(r['res']['gaps'])} mục cần người quyết, "
          f"{len(r['res']['warnings'])} cảnh báo")
    return (n_ok, tot)


def main(argv):
    con = db.connect()
    bom.seed_rules(con)
    flt = None
    if "--machine" in argv:
        flt = argv[argv.index("--machine") + 1]
    total_ok = total = 0
    for m in con.execute("select * from machine where is_golden=1"):
        if flt and flt not in (m["notes"] or ""):
            continue
        r = compare(con, m)
        if r is None:
            print(f"  (bỏ qua {m['name'][:40]}: không có actuator nào parse được)")
            continue
        ok, t = show(r)
        total_ok += ok
        total += t
        print()
    if total:
        print("═" * 84)
        print(f"  TỔNG: {total_ok}/{total} dòng đúng hoàn toàn = {total_ok/total*100:.0f}%")
        print("═" * 84)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
