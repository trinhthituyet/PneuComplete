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
        """select s.id, s.code, s.catalog_id, s.name, s.part_prefix
           from series s
           where exists (select 1 from code_slot cs where cs.series_id = s.id)"""
    ).fetchall()
    for r in rows:
        # Tiền tố khai tường minh thì tin nó. Nhưng vẫn phải sinh CẶP biến thể
        # nam châm: SMC chèn 'D' sau chữ đầu để chỉ loại có nam châm sẵn
        # (CM2→CDM2, CQS→CDQS). part_prefix ghi bản có nam châm ('CDM2') nên nếu
        # chỉ dùng đúng chuỗi đó thì mã 'CM2B40-150AZ' không parse được, và
        # has_magnet của bản CDM2 cũng bị mất.
        if r["part_prefix"]:
            pref = r["part_prefix"].upper()
            base = re.sub(r"^([A-Z])D", r"\1", pref)
            out.append({"series_id": r["id"], "code": r["code"], "name": r["name"],
                        "prefix": pref, "has_magnet": base != pref})
            if base != pref:
                out.append({"series_id": r["id"], "code": r["code"], "name": r["name"],
                            "prefix": base, "has_magnet": False})
            continue
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
            "pad": s["pad"],
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
    """Thử MỌI series có tiền tố khớp, chọn bản parse trọn vẹn nhất.

    Cần thử hết vì nhiều series dùng chung tiền tố: 'AS2201F-01-06S' thuộc AS-E-E
    (núm thường) còn 'AS2201F-01-06SA' thuộc AS1-E (push-lock). Chỉ thử ứng viên
    đầu tiên là chọn sai ngữ pháp và báo dư ký tự.
    """
    pn = part_number.strip().upper().replace(" ", "")

    # ── Hậu tố NGOÀI CATALOG ─────────────────────────────────────────────────
    # Một số đơn hàng mang hậu tố riêng không có trong catalog. Đo được trên BOM
    # thật: máy 24-236 có 5/6 mã SMC kết thúc "-NA" (SY5100-5UE1-NA,
    # SS5Y5-10SVA-13B-C6A-NA, SY50M-26-1A-NA…), máy 23-432 thì 0/6. Tìm khắp
    # catalog SY plug-in không có bảng nào giải nghĩa "-NA".
    #
    # → Đây là hậu tố áp cho CẢ ĐƠN HÀNG, không phải một ô mã. Tách ra để đọc
    # được phần thân, và GHI LẠI trong attrs thay vì bỏ im lặng — người dùng phải
    # biết engine đã lược bỏ cái gì.
    order_suffix = None
    m_sfx = re.match(r"^(.*?)-(NA)$", pn)
    if m_sfx and len(m_sfx.group(1)) >= 4:
        pn, order_suffix = m_sfx.group(1), m_sfx.group(2)

    # ── BẢNG TRA trước ngữ pháp ──────────────────────────────────────────────
    # Một số mã KHÔNG sinh từ ngữ pháp mà nằm sẵn trong bảng `part` dưới dạng
    # bảng tra đọc tay từ catalog: gasket, end plate manifold (SY5000-26-20A,
    # SY5000-GS-1 — trang 45/73 của PDF SY3000).
    #
    # LỖI CŨ: parser chỉ đi qua ngữ pháp. Các mã đó gắn vào series SY-5-E, mà
    # ngữ pháp series đó là NGỮ PHÁP VAN (SY5220-5MZE-C6) — nên nó thử đọc
    # "SY5000-26-20A" như một mã van và báo dư "0-26-20A". Kết quả: engine SINH
    # được mã nhưng không ĐỌC ngược được chính mã mình sinh ra.
    #
    # Tra bảng đi TRƯỚC vì nó là dữ kiện đã đọc từ catalog, chắc chắn hơn suy
    # luận từ ngữ pháp.
    # CHỈ nhận mã có `role` trong attrs — đó là dấu của bảng tra ĐỌC TAY TỪ
    # CATALOG (gasket, end_plate). Nhận mọi dòng `part` là sai: bảng đó còn chứa
    # mã do chính engine ghi vào lúc materialize, và lấy chúng làm nguồn sự thật
    # thì parser đọc lại kết quả của chính mình thay vì đọc catalog — sai lệch
    # nào của engine sẽ tự khẳng định là đúng.
    row = con.execute(
        """select p.part_number, p.attrs, s.code, s.catalog_id, s.name
           from part p join series s on s.id = p.series_id
           where p.part_number = ?
             and json_valid(p.attrs)
             and json_extract(p.attrs, '$.role') is not null""", (pn,)).fetchone()
    if row:
        attrs = json.loads(row["attrs"] or "{}")
        clean = {k: v for k, v in attrs.items() if not k.startswith("_")}
        if order_suffix:
            clean["order_suffix"] = order_suffix
        return {"ok": True, "series": row["code"], "series_name": row["name"],
                "catalog_id": row["catalog_id"],
                "order_suffix": order_suffix,
                "attrs": clean,
                "trace": [(k, str(v), k) for k, v in attrs.items()
                          if not k.startswith("_")],
                "unparsed": None, "missing": None,
                "source": "bảng tra trong catalog", "input": part_number}

    attempts = []
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
                    opt_attrs[slot["name"]] = int(m.group(1))
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

            # Một số ô có mã trùng nhau ở hai nghĩa khác nhau: ô port_size của KQ2
            # vừa mang cỡ ren ('08' không tồn tại) vừa mang cỡ ống thứ hai của
            # union khác đường kính ('08' → ø8). Biến thể sau khai hậu tố 'x' để
            # phân biệt trong DB nhưng khớp cùng chuỗi số trong mã hàng.
            cands = [(o, o["code"]) for o in slot["options"]] + \
                    [(o, o["code"][:-1]) for o in slot["options"]
                     if o["code"].endswith("x")]
            cands.sort(key=lambda c: -len(c[1]))
            hit = next((o for o, lit in cands
                        if lit.lower() not in NIL and rest.startswith(lit)), None)
            if hit:
                lit = hit["code"][:-1] if hit["code"].endswith("x") else hit["code"]
                got[slot["name"]] = hit["code"]
                trace.append((slot["name"], hit["code"], hit["label"]))
                opt_attrs.update(hit["attrs"])
                rest = rest[len(lit):]
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

        attempts.append({
            "ok": rest == "" and not missing,
            "missing": missing or None,
            "series_id": cand["series_id"], "series": cand["code"],
            "series_name": cand["name"], "prefix": cand["prefix"],
            "has_magnet": cand["has_magnet"],
            "slots": got, "attrs": attrs, "trace": trace,
            "unparsed": rest or None,
        })

    if not attempts:
        return {"ok": False, "error": "không nhận ra series nào có ngữ pháp",
                "input": part_number}
    # ưu tiên: parse trọn vẹn > ít ký tự dư > ít ô thiếu > khớp nhiều ô hơn
    attempts.sort(key=lambda a: (not a["ok"], len(a["unparsed"] or ""),
                                 len(a["missing"] or []), -len(a["slots"])))
    return attempts[0]
