"""Nạp ngữ pháp nhập tay từ db/seed/grammar/*.yaml vào code_slot + code_option.

Dùng cho series mà parser PDF không đọc được sơ đồ (xem docs/CRAWL-RESULTS.md).
Ngữ pháp nhập tay được coi là ĐÃ XÁC MINH (`is_verified`-tương đương) vì có người
đọc trực tiếp sơ đồ, nhưng vẫn ghi `source` để truy nguồn.

    python3 -m crawler.grammar_seed            # nạp tất cả
    python3 -m crawler.grammar_seed tu.yaml    # nạp 1 file
"""
import json
import sys
from pathlib import Path

import yaml

from . import db

SEED_DIR = db.ROOT / "db" / "seed" / "grammar"


def load_file(con, path: Path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    cid = spec["series_catalog_id"]
    row = con.execute("select id, code from series where catalog_id=?", (cid,)).fetchone()
    if not row and "create_series" in spec:
        # series tổng hợp: dữ liệu có thật nhưng không có trang series riêng trên
        # webcatalog (ví dụ D-M9 trích từ bảng applicable switch của catalog CM2)
        cs = spec["create_series"]
        cat = None
        if cs.get("category_slug"):
            con.execute("insert or ignore into category (code, name, layer) values (?,?,?)",
                        (cs["category_slug"], cs["category_slug"].replace("-", " ").title(),
                         "electrical"))
            cat = con.execute("select id from category where code=?",
                              (cs["category_slug"],)).fetchone()["id"]
        con.execute(
            """insert into series (code, catalog_id, name, category_id, notes)
               values (?,?,?,?,?)""",
            (cs["code"], cid, cs.get("name"), cat,
             f"series tổng hợp, nguồn: {spec.get('source', '')}"),
        )
        con.commit()
        row = con.execute("select id, code from series where catalog_id=?", (cid,)).fetchone()
    if not row:
        return {"file": path.name, "error": f"không có series catalog_id={cid}"}
    sid = row["id"]

    # ngữ pháp nhập tay thay thế hoàn toàn ngữ pháp máy đọc cho series đó
    con.execute("delete from code_slot where series_id=?", (sid,))

    n_slot = n_opt = 0
    for s in spec["slots"]:
        con.execute(
            """insert into code_slot (series_id, pos, name, value_type, separator)
               values (?,?,?,?,?)
               on conflict (series_id, pos) do update set
                 name=excluded.name, value_type=excluded.value_type,
                 separator=excluded.separator""",
            (sid, s["pos"], s["name"], s["value_type"], s.get("separator", "")),
        )
        slot_id = con.execute(
            "select id from code_slot where series_id=? and pos=?", (sid, s["pos"])
        ).fetchone()["id"]
        n_slot += 1
        for o in s.get("options", []):
            con.execute(
                """insert into code_option (slot_id, code, label, attrs, requires)
                   values (?,?,?,?,?)
                   on conflict (slot_id, code) do update set
                     label=excluded.label, attrs=excluded.attrs,
                     requires=excluded.requires""",
                (slot_id, str(o["code"]), o.get("label"),
                 json.dumps(o.get("attrs", {}), ensure_ascii=False),
                 json.dumps(o.get("requires", {}), ensure_ascii=False)),
            )
            n_opt += 1
        if s["value_type"] == "integer" and "range" in s:
            r = s["range"]
            con.execute(
                """insert into code_range (slot_id, min_val, max_val, step, unit)
                   values (?,?,?,?,?) on conflict (slot_id) do update set
                     min_val=excluded.min_val, max_val=excluded.max_val,
                     step=excluded.step, unit=excluded.unit""",
                (slot_id, r["min"], r["max"], r.get("step"), r.get("unit")),
            )

    con.execute("update series set notes=coalesce(notes,'')||? where id=?",
                (f" | ngữ pháp nhập tay từ {path.name}: {spec.get('source','')}", sid))
    con.commit()
    return {"file": path.name, "series": row["code"], "slots": n_slot, "options": n_opt}


def main(argv):
    con = db.connect()
    files = [SEED_DIR / a for a in argv] if argv else sorted(SEED_DIR.glob("*.yaml"))
    if not files:
        print(f"không có file nào trong {SEED_DIR}")
        return 1
    for f in files:
        res = load_file(con, f)
        if "error" in res:
            print(f"  ✗ {res['file']}: {res['error']}")
        else:
            print(f"  ✓ {res['file']:16} {res['series']:16} "
                  f"{res['slots']} ô, {res['options']} option")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
