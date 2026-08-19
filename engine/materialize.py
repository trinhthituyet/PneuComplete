"""Materialize mã hàng thành `part` + `part_interface`, và ghép giao diện.

Hai việc:
  1. materialize(): mã hàng (chuỗi) → dòng `part` thật + các `part_interface` của nó,
     sinh từ template trong db/seed/interfaces.yaml theo attrs đã parse.
  2. mates(): hai giao diện có lắp được với nhau không.

Nguyên tắc: interface là thứ engine suy luận trên đó, KHÔNG phải tên sản phẩm.
Thêm hãng khác chỉ cần thêm template, không sửa code.
"""
import json
from pathlib import Path

from crawler import db
from engine import conf, parser

TEMPLATES = db.ROOT / "db" / "seed" / "interfaces.yaml"

# Ren nào lắp được vào ren nào. R (côn ngoài) vào Rc (côn trong) là chuẩn Nhật.
# G là ren trụ song song, KHÔNG lắp an toàn vào Rc. NPT chỉ lắp NPT.
THREAD_COMPAT = [
    ("R", "Rc", True, "R male vào Rc female — chuẩn ISO 7 / JIS, kín bằng ren côn"),
    ("R", "R", True, "cùng hệ ren côn"),
    ("NPT", "NPT", True, "cùng hệ NPT"),
    ("G", "G", True, "cùng hệ ren trụ, kín bằng gasket"),
    ("M", "M", True, "ren mét"),
    ("R", "NPT", False, "khác góc ren và bước — rò khí dù đường kính danh nghĩa giống"),
    ("NPT", "Rc", False, "khác góc ren (60° vs 55°)"),
    ("G", "Rc", False, "ren trụ vào ren côn — không kín"),
    ("R", "G", False, "ren côn vào ren trụ — không kín"),
]


def seed_thread_compat(con):
    for m, f, ok, note in THREAD_COMPAT:
        con.execute(
            """insert into thread_compat (male_standard, female_standard, is_ok, note)
               values (?,?,?,?) on conflict (male_standard, female_standard)
               do update set is_ok=excluded.is_ok, note=excluded.note""",
            (m, f, 1 if ok else 0, note),
        )
    con.commit()


def load_templates():
    raw = conf.load(TEMPLATES)
    return {t["series_catalog_id"]: t for t in raw}


def _lookup(spec_by, attrs):
    """Tra bảng `{attr, map}` — chịu được cả khoá số và khoá chuỗi.

    Cần thiết vì cùng một bảng tồn tại ở hai định dạng: YAML cho phép khoá SỐ
    NGUYÊN (`map: {20: "1/8", 32: "1/8"}`) còn JSON chỉ có khoá CHUỖI ("20","32").
    Giá trị đem tra thường là float (bore_mm = 32.0), nên str(32.0) = "32.0" KHÔNG
    khớp khoá "32". Lỗi thật đã gặp khi chuyển cấu hình sang JSON: mọi cỡ cửa khí
    biến thành None và engine báo "thiếu dữ liệu port_size".
    """
    val = attrs.get(spec_by["attr"])
    if val is None:
        return None
    m = spec_by["map"]
    keys = [val, str(val)]
    if isinstance(val, float) and val.is_integer():
        keys += [int(val), str(int(val))]
    elif isinstance(val, int):
        keys += [float(val), str(float(val))]
    for k in keys:
        try:
            if k in m:
                return m[k]
        except TypeError:
            continue
    return None


def _resolve(spec, key, parsed):
    """Lấy giá trị 1 field của interface từ hằng số / attrs / bảng tra / ô mã.

    Thứ tự ưu tiên: hằng số → bảng tra (*_by) → attrs → ô mã (*_from_slot).
    Bảng tra đứng trước ô mã để xử lý ngoại lệ theo cỡ: MGP ø12/ø16 chỉ có ren
    mét M5 x 0.8 (ghi chú catalog trang 10), còn ø20+ theo ô port_thread. Bảng
    chỉ khai 12/16, các bore khác trả None và rơi xuống ô mã.
    """
    attrs, slots = parsed["attrs"], parsed["slots"]
    if key in spec:
        return spec[key]
    if f"{key}_by" in spec:
        got = _lookup(spec[f"{key}_by"], attrs)
        if got is not None:
            return got
    if f"{key}_from_attr" in spec:
        got = attrs.get(spec[f"{key}_from_attr"])
        if got is not None:
            return got
    if f"{key}_from_slot" in spec:
        s = spec[f"{key}_from_slot"]
        code = slots.get(s["slot"])
        return s.get("map", {}).get(code, s.get("default"))
    return None


def materialize(con, part_number, templates=None):
    """Mã hàng → part_id. Idempotent: gọi lại trả về đúng dòng cũ."""
    p = parser.parse(con, part_number)
    if not p.get("ok"):
        return {"ok": False, "part_number": part_number,
                "error": p.get("error") or f"chưa parse được (dư: {p.get('unparsed')}, "
                                           f"thiếu: {p.get('missing')})",
                "parsed": p}
    templates = templates or load_templates()

    con.execute(
        """insert or ignore into part (part_number, series_id, description, attrs)
           values (?,?,?,?)""",
        (part_number.upper(), p["series_id"], p["series_name"],
         json.dumps(p["attrs"], ensure_ascii=False)),
    )
    row = con.execute("select id from part where part_number=?",
                      (part_number.upper(),)).fetchone()
    pid = row["id"]
    # attrs có thể phong phú hơn lần trước (grammar được cải thiện) → cập nhật
    con.execute("update part set attrs=?, series_id=? where id=?",
                (json.dumps(p["attrs"], ensure_ascii=False), p["series_id"], pid))

    cid = con.execute("select catalog_id from series where id=?",
                      (p["series_id"],)).fetchone()["catalog_id"]
    tpl = templates.get(cid)
    made = []
    if tpl:
        con.execute("delete from part_interface where part_id=?", (pid,))
        for spec in tpl.get("interfaces") or []:
            when = spec.get("when") or {}
            if any(p["attrs"].get(k) != v for k, v in when.items()):
                continue
            iface = {
                "role": spec["role"], "kind": spec["kind"],
                "gender": spec.get("gender"),
                "standard": _resolve(spec, "standard", p),
                "size": _resolve(spec, "size", p),
                "tube_od_mm": _resolve(spec, "tube_od", p),
                "qty": spec.get("qty", 1),
            }
            if iface["kind"] == "thread" and not (iface["standard"] and iface["size"]):
                continue          # check constraint của bảng sẽ chặn, bỏ sớm cho rõ
            con.execute(
                """insert into part_interface
                   (part_id, role, kind, gender, standard, size, tube_od_mm, qty, attrs)
                   values (?,?,?,?,?,?,?,?,?)""",
                (pid, iface["role"], iface["kind"], iface["gender"], iface["standard"],
                 iface["size"], iface["tube_od_mm"], iface["qty"],
                 json.dumps({"source": tpl.get("source", "")[:200]}, ensure_ascii=False)),
            )
            made.append(iface)
    con.commit()
    return {"ok": True, "part_id": pid, "part_number": part_number.upper(),
            "series_id": p["series_id"], "attrs": p["attrs"],
            "interfaces": made, "has_template": tpl is not None,
            "trace": p["trace"]}


def mates(con, a, b):
    """a lắp được vào b? a/b là dict interface (hoặc sqlite3.Row)."""
    ka, kb = a["kind"], b["kind"]
    if ka == "thread" and kb == "thread":
        ga, gb = a["gender"], b["gender"]
        if {ga, gb} != {"male", "female"}:
            return False, "cần một đầu male và một đầu female"
        male, female = (a, b) if ga == "male" else (b, a)
        if (male["size"] or "") != (female["size"] or ""):
            return False, f"cỡ ren khác nhau: {male['size']} vs {female['size']}"
        r = con.execute(
            "select is_ok, note from thread_compat where male_standard=? and female_standard=?",
            (male["standard"], female["standard"]),
        ).fetchone()
        if r is None:
            return False, (f"chưa có dữ liệu tương thích ren "
                           f"{male['standard']} male → {female['standard']} female")
        return bool(r["is_ok"]), r["note"]

    if {ka, kb} == {"onetouch", "tube"} or (ka == "tube" and kb == "tube"):
        oa, ob = a["tube_od_mm"], b["tube_od_mm"]
        if oa is None or ob is None:
            return False, "thiếu đường kính ống"
        if abs(float(oa) - float(ob)) > 1e-6:
            return False, f"ống ø{oa} không cắm vào đầu ø{ob}"
        return True, f"one-touch ø{oa}"

    if ka == "rail" and kb == "rail":
        if a["standard"] != b["standard"]:
            return False, f"rãnh khác chuẩn: {a['standard']} vs {b['standard']}"
        return True, f"rãnh gắn {a['standard']}"

    return False, f"không có luật ghép cho {ka} ↔ {kb}"
