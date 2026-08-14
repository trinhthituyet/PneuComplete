"""Parse mã hàng → spec, dùng ngữ pháp trong code_slot/code_option.

Đây là chiều ngược của How-to-Order: catalog nói "ghép ô lại thành mã", còn ở đây
ta tách mã ra thành spec để engine suy luận.

    >>> parse(con, "CDM2L32-500Z")
    {'series': 'CM2/CDM2-Z', 'has_magnet': True,
     'slots': {'mounting': 'L', 'bore': '32', 'stroke': 500, ...},
     'attrs': {'bore_mm': 32.0, 'stroke_mm': 500, ...}}

Nguyên tắc: chỉ nhận khi tiêu thụ hết ký tự. Còn dư ký tự nghĩa là ngữ pháp chưa
đủ — trả `unparsed` để người dùng biết chỗ nào chưa hiểu, KHÔNG đoán bừa.
"""
import json
import re

NIL = {"nil", "none", ""}


def series_candidates(con):
    """Các series đã có ngữ pháp, kèm tiền tố nhận dạng.

    series.code hay ở dạng nhóm ('CM2/CDM2-Z') gộp cả bản thường và bản có nam
    châm. Tách ra thành từng tiền tố, và đánh dấu bản có 'D' chèn sau chữ đầu là
    loại có nam châm sẵn (quy ước của SMC: CM2 → CDM2).
    """
    out = []
    rows = con.execute(
        """select s.id, s.code, s.catalog_id, s.name
           from series s
           where exists (select 1 from code_slot cs where cs.series_id = s.id)"""
    ).fetchall()
    for r in rows:
        raw = (r["code"] or "") + "/" + (r["catalog_id"] or "")
        raw = re.sub(r"-E$", "", raw)
        prefixes = set()
        for part in re.split(r"[/\-]", raw):
            part = part.strip().upper()
            if re.fullmatch(r"[A-Z]{1,4}\d{0,3}[A-Z]?", part) and len(part) >= 2:
                prefixes.add(part)
        # Mã như 'D-M9BW' có tiền tố là 'D-': chữ đầu + gạch nối. Không thêm dạng
        # này thì series 'D-M9' sinh ra tiền tố 'M9' và không khớp mã thật.
        first = (r["code"] or "").split("-")[0].strip().upper()
        if first and len(first) <= 2 and "-" in (r["code"] or ""):
            prefixes.add(first + "-")
        bases = {p for p in prefixes if not re.match(r"^[A-Z]D", p)}
        for p in prefixes:
            base = re.sub(r"^([A-Z])D", r"\1", p)
            out.append({
                "series_id": r["id"], "code": r["code"], "name": r["name"],
                "prefix": p, "has_magnet": p != base and base in bases,
            })
    out.sort(key=lambda c: -len(c["prefix"]))     # tiền tố dài khớp trước
    return out


def grammar(con, series_id):
    slots = con.execute(
        "select * from code_slot where series_id=? order by pos", (series_id,)
    ).fetchall()
    g = []
    for s in slots:
        opts = con.execute(
            "select code, label, attrs, requires from code_option where slot_id=?", (s["id"],)
        ).fetchall()
        g.append({
            "pos": s["pos"], "name": s["name"], "value_type": s["value_type"],
            "separator": s["separator"], "is_required": bool(s["is_required"]),
            # option dài khớp trước: 'BZ' phải thắng 'B'
            "options": sorted(
                [{"code": o["code"], "label": o["label"],
                  "attrs": json.loads(o["attrs"] or "{}"),
                  "requires": json.loads(o["requires"] or "{}")} for o in opts],
                key=lambda o: -len(o["code"]),
            ),
        })
    return g


def parse(con, part_number: str):
    pn = part_number.strip().upper().replace(" ", "")
    for cand in series_candidates(con):
        if not pn.startswith(cand["prefix"]):
            continue
        rest = pn[len(cand["prefix"]):]
        g = grammar(con, cand["series_id"])
        got, trace, missing = {}, [], []
        opt_attrs = {}
        for slot in g:
            sep = slot["separator"]
            if sep and rest.startswith(sep):
                rest = rest[len(sep):]

            if slot["value_type"] == "integer":
                m = re.match(r"^(\d{1,5})", rest)
                if m:
                    got[slot["name"]] = int(m.group(1))
                    trace.append((slot["name"], m.group(1), None))
                    rest = rest[m.end():]
                elif slot["is_required"]:
                    missing.append(slot["name"])
                continue

            if slot["value_type"] == "free":
                # ô tự do (auto switch): mã thật hay có dấu '-' phía trước
                # ('CDM2B32-100AZ-M9BW') nhưng sơ đồ How-to-Order không thể hiện
                # dấu này, nên nhận cả hai dạng.
                m = re.match(r"^-?([A-Z]\d[A-Z0-9]{1,5})$", rest)
                if m:
                    got[slot["name"]] = m.group(1)
                    trace.append((slot["name"], m.group(1), None))
                    rest = rest[m.end():]
                continue

            hit = next((o for o in slot["options"]
                        if o["code"].lower() not in NIL and rest.startswith(o["code"])), None)
            if hit:
                got[slot["name"]] = hit["code"]
                trace.append((slot["name"], hit["code"], hit["label"]))
                opt_attrs.update(hit["attrs"])
                rest = rest[len(hit["code"]):]
            else:
                nil = next((o for o in slot["options"] if o["code"].lower() in NIL), None)
                if nil:                       # ô có giá trị mặc định, lược khỏi mã
                    got[slot["name"]] = nil["code"]
                    trace.append((slot["name"], nil["code"], nil["label"]))
                    opt_attrs.update(nil["attrs"])
                elif slot["is_required"]:
                    # ô bắt buộc không khớp gì: mã thiếu phần này, KHÔNG coi là hợp lệ
                    missing.append(slot["name"])

        attrs = dict(opt_attrs)
        if got.get("bore"):
            attrs["bore_mm"] = float(got["bore"])
        if got.get("stroke"):
            attrs["stroke_mm"] = got["stroke"]
        if cand["has_magnet"]:
            attrs["has_magnet"] = True
        if got.get("cushion"):
            lbl = next((t[2] for t in trace if t[0] == "cushion"), "") or ""
            attrs["cushion"] = "air" if "air" in lbl.lower() else "rubber_bumper"
        if got.get("auto_switch"):
            attrs["auto_switch"] = got["auto_switch"]

        return {
            "ok": rest == "" and not missing,
            "missing": missing or None,
            "series_id": cand["series_id"], "series": cand["code"],
            "series_name": cand["name"], "prefix": cand["prefix"],
            "has_magnet": cand["has_magnet"],
            "slots": got, "attrs": attrs, "trace": trace,
            "unparsed": rest or None,
        }
    return {"ok": False, "error": "không nhận ra series nào có ngữ pháp",
            "input": part_number}
