"""Nạp BOM máy cũ (購入品リスト) vào bảng machine + bom_line, rồi đo độ phủ.

    python3 -m ingest.bom_import BOM/*.xlsx
    python3 -m ingest.bom_import --report

Cấu trúc file thật (2 máy của JNC, mẫu của công ty):
    sheet '案件名入力'  : thông tin máy (製番 = số máy, 案件名 = tên, 客先 = khách)
    sheet '(A)…(F)…'   : từng bộ phận cơ khí, có xy-lanh nằm rải rác
    sheet '(P)圧空部'   : phần khí nén tập trung (van, ống, fitting, FRL)
Cột: 6=品名 (mô tả), 8=仕様 (MÃ HÀNG), 9=メーカー (hãng), 10=数量 (số lượng), 11=備考
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler import db          # noqa: E402
from ingest import xlsx         # noqa: E402

C_DESC, C_SPEC, C_MAKER, C_QTY, C_NOTE = 6, 8, 9, 10, 11

# suy tầng BOM từ mã hàng — chỉ để thống kê, không dùng cho suy luận
LAYER = [
    (r"^(C[DJMQ]|MX|MG|CX|MH|MY|RS|CY|ML|CE|LE|JA|JB)", "actuator"),
    (r"^(SY|SS5Y|VQ|VT|VF|VZ|SJ)", "valve"),
    (r"^(AC|AR|AW|AF|AL|AMC|AN|IR)", "air_prep"),
    (r"^(KQ|KS|TU|PUT|T[0-9])", "piping"),
    (r"^(AS)", "accessory"),
    (r"^(D-|ISE|ZS|PCA|SW)", "electrical"),
]


def layer_of(code):
    for pat, lay in LAYER:
        if re.match(pat, code, re.I):
            return lay
    return "other"


def read_machine(path):
    """Trả (meta, [dòng vật tư])."""
    meta = {"name": path.name, "code": None, "customer": None}
    try:
        for r in xlsx.read(path, "案件名入力"):
            if len(r) > 3 and r[1]:
                if "製番" in r[1]:
                    meta["code"] = r[3]
                elif "案件名" in r[1]:
                    meta["name"] = r[3]
                elif "客先" in r[1]:
                    meta["customer"] = r[3]
    except (ValueError, IndexError):
        pass

    lines = []
    for sh in xlsx.sheet_names(path):
        if sh == "案件名入力":
            continue
        for r in xlsx.read(path, sh):
            if len(r) <= C_QTY:
                continue
            spec, maker = (r[C_SPEC] or "").strip(), (r[C_MAKER] or "").strip()
            if not spec or not maker:
                continue
            try:
                qty = int(float((r[C_QTY] or "0").replace(",", "")))
            except ValueError:
                qty = 0
            lines.append({
                "sheet": sh, "raw_code": spec, "maker": maker, "qty": qty,
                "raw_desc": (r[C_DESC] or "").strip(),
                "note": (r[C_NOTE] or "").strip() if len(r) > C_NOTE else "",
                "layer": layer_of(spec),
            })
    return meta, lines


def import_file(con, path):
    meta, lines = read_machine(path)
    con.execute("delete from machine where name=?", (meta["name"],))
    cur = con.execute(
        "insert into machine (name, customer, is_golden, notes) values (?,?,1,?)",
        (meta["name"], meta["customer"], f"製番 {meta['code']} · nguồn {path.name}"))
    mid = cur.lastrowid
    for l in lines:
        con.execute(
            """insert into bom_line (machine_id, raw_code, raw_desc, qty, layer)
               values (?,?,?,?,?)""",
            (mid, l["raw_code"], f"[{l['sheet']}] {l['maker']} {l['raw_desc']} {l['note']}".strip(),
             l["qty"], l["layer"]))
    con.commit()
    return mid, meta, lines


def match_parts(con):
    """Khớp raw_code → part. Hai đường: ngữ pháp, hoặc mã đã có sẵn trong `part`.

    Đường thứ hai cần thiết vì một số họ KHÔNG có ngữ pháp ghép mà là BẢNG TRA —
    gasket SY□000-GS-1, end plate SY□000-26-□□ tra theo (series, kiểu manifold).
    Trước đó chỉ dùng parser nên các mã này bị tính là 'chưa khớp' dù đã có trong DB.
    """
    from engine import parser as P

    ok = fail = 0
    for r in con.execute("select id, raw_code from bom_line where part_id is null"):
        exact = con.execute("select id from part where part_number=?",
                            (r["raw_code"].upper(),)).fetchone()
        if exact:
            con.execute("update bom_line set part_id=? where id=?", (exact["id"], r["id"]))
            ok += 1
            continue
        res = P.parse(con, r["raw_code"])
        if res.get("ok"):
            con.execute(
                """insert or ignore into part (part_number, series_id, attrs)
                   values (?,?,'{}')""", (r["raw_code"].upper(), res["series_id"]))
            p = con.execute("select id from part where part_number=?",
                            (r["raw_code"].upper(),)).fetchone()
            con.execute("update bom_line set part_id=? where id=?", (p["id"], r["id"]))
            ok += 1
        else:
            fail += 1
    con.commit()
    return ok, fail


def report(con):
    import collections

    print("═" * 84)
    print("ĐỘ PHỦ TRÊN BOM MÁY THẬT")
    print("═" * 84)
    for m in con.execute("select * from machine where is_golden=1"):
        rows = con.execute(
            "select * from bom_line where machine_id=?", (m["id"],)).fetchall()
        smc = [r for r in rows if "SMC" in (r["raw_desc"] or "").upper()]
        matched = [r for r in smc if r["part_id"]]
        print(f"\n  {m['name'][:52]}")
        print(f"    {m['notes']}")
        print(f"    {len(rows)} dòng vật tư · {len(smc)} dòng SMC · "
              f"parse được {len(matched)}/{len(smc)}")
        by = collections.Counter(r["layer"] for r in smc)
        got = collections.Counter(r["layer"] for r in matched)
        for lay in ("actuator", "valve", "air_prep", "piping", "accessory",
                    "electrical", "other"):
            if by[lay]:
                print(f"      {lay:11} {got[lay]:3}/{by[lay]:<3} dòng")

    print("\n" + "═" * 84)
    print("HỌ SẢN PHẨM CHƯA CÓ NGỮ PHÁP — xếp theo số dòng BOM")
    print("═" * 84)
    miss = collections.Counter()
    qty = collections.Counter()
    for r in con.execute("""select raw_code, qty, layer from bom_line
                            where part_id is null and raw_desc like '%SMC%'"""):
        fam = re.match(r"^([A-Z]+\d{0,4})", r["raw_code"].upper())
        k = (r["layer"], fam.group(1) if fam else "?")
        miss[k] += 1
        qty[k] += r["qty"] or 0
    for (lay, fam), n in miss.most_common(22):
        print(f"  {lay:11} {fam:12} {n:3} dòng, {qty[(lay,fam)]:4} cái")
    con.commit()


def main(argv):
    con = db.connect()
    if "--report" in argv:
        report(con)
        return 0
    files = [Path(a) for a in argv if a.endswith(".xlsx")]
    if not files:
        print(__doc__)
        return 1
    for f in files:
        mid, meta, lines = import_file(con, f)
        print(f"  ✓ {f.name[:48]:50} {len(lines):3} dòng → machine #{mid}")
    ok, fail = match_parts(con)
    print(f"\n  khớp ngữ pháp: {ok} · chưa khớp: {fail}\n")
    report(con)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
