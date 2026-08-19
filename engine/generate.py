"""Sinh mã hàng từ ngữ pháp — chiều ngược của engine/parser.py.

    >>> generate(con, series_id_AS, {"port_size": "1/8", "tube_od_mm": 6.0,
    ...                              "control": "meter_out", "sealant": True})
    {'ok': True, 'part_number': 'AS2201F-01-06S', ...}

Nguyên tắc: ô nào không suy được thì BÁO, không chọn bừa. Trả `undecided` để
engine đẩy thành `status='gap'` cho người quyết định — thà thiếu hơn sai mã.
"""
from engine.parser import NIL, grammar


def _match(opt, want):
    """Option có thoả các ràng buộc trong want? Chỉ xét khoá mà option có khai."""
    hits = 0
    for k, v in want.items():
        # option có thể khai dạng số nhiều là danh sách: body_size khai
        # port_sizes: ["1/8","1/4"] để khớp với want port_size: "1/8"
        key = k if k in opt["attrs"] else (f"{k}s" if f"{k}s" in opt["attrs"] else None)
        if key is None:
            continue
        av = opt["attrs"][key]
        if isinstance(av, list):
            if v not in av:
                return None
        elif isinstance(av, float) or isinstance(v, float):
            try:
                if abs(float(av) - float(v)) > 1e-6:
                    return None
            except (TypeError, ValueError):
                return None
        elif av != v:
            return None
        hits += 1
    return hits


def generate(con, series_id, want, prefix=None, soft=()):
    """want: dict thuộc tính mong muốn (khớp với attrs của option).

    soft: tên các khoá chỉ là SỞ THÍCH. Nếu không option nào thoả thì bỏ ràng buộc
    đó và chọn giá trị mặc định, kèm ghi chú — thay vì báo gap. Cần thiết vì nhiều
    lựa chọn không tồn tại ở mọi cỡ: speed controller cỡ M5 KHÔNG có loại sealant
    (ghi chú trong catalog AS), nên yêu cầu 'có sealant' phải tự nhượng bộ.
    """
    relaxed = []
    g = grammar(con, series_id)
    if not g:
        return {"ok": False, "error": "series chưa có ngữ pháp"}

    row = con.execute("select code, catalog_id, name, part_prefix from series where id=?",
                      (series_id,)).fetchone()
    if prefix is None:
        # part_prefix khai tường minh là nguồn tin cậy duy nhất. Suy từ series.code
        # sinh ra rác khi code là câu chữ: 'AS Push-lock Type' → 'AS PUSH'.
        prefix = (row["part_prefix"] or "").strip().upper()
    if not prefix:
        prefix = (row["code"] or "").split("/")[0].split("-")[0].strip().upper()
        if not prefix.isalnum():
            return {"ok": False,
                    "error": f"series '{row['code']}' chưa khai part_prefix — "
                             f"không suy được tiền tố mã hàng"}

    out, chosen, undecided = prefix, {}, []
    for slot in g:
        opts = slot["options"]
        if slot["value_type"] == "integer":
            v = want.get(slot["name"])
            if v is None:
                undecided.append({"slot": slot["name"], "reason": "cần giá trị số"})
                continue
            # đệm 0 nếu ô khai `pad`: số station SS5Y phải là '05', không phải '5'
            txt = str(int(v)).zfill(slot.get("pad") or 0)
            out += slot["separator"] + txt
            chosen[slot["name"]] = int(v)
            continue

        if not opts:                      # ô free (auto switch) — bỏ nếu không yêu cầu
            v = want.get(slot["name"])
            if v:
                out += slot["separator"] + str(v)
                chosen[slot["name"]] = v
            continue

        # want có khoá trùng TÊN Ô → chỉ định trực tiếp mã option
        # (ví dụ {"color": "BU"} cho ô color, vì option màu không khai attrs)
        direct = want.get(slot["name"])
        if direct is not None and any(o["code"] == str(direct) for o in opts):
            o = next(o for o in opts if o["code"] == str(direct))
            chosen[slot["name"]] = o["code"]
            if o["code"].lower() not in NIL:
                out += slot["separator"] + o["code"]
            continue

        # loại option có điều kiện `requires` mà các ô đã chọn không thoả
        ok_opts = []
        for o in opts:
            req = o.get("requires") or {}
            bad = False
            for rk, rv in req.items():
                cv = chosen.get(rk)
                if cv is None:
                    continue
                allowed = rv if isinstance(rv, list) else [rv]
                if str(cv) not in [str(a) for a in allowed]:
                    bad = True
                    break
            if not bad:
                ok_opts.append(o)
        opts = ok_opts or opts
        scored = [(s, o) for o in opts if (s := _match(o, want)) is not None]
        if not scored and soft:
            # thử lại sau khi bỏ các ràng buộc mềm liên quan tới ô này
            hard = {k: v for k, v in want.items() if k not in soft}
            scored = [(s, o) for o in opts if (s := _match(o, hard)) is not None]
            if scored:
                dropped = [k for k in soft if k in want]
                relaxed.append({"slot": slot["name"], "dropped": dropped})
        if not scored:
            undecided.append({"slot": slot["name"],
                              "reason": "không option nào thoả ràng buộc",
                              "options": [o["code"] for o in opts][:8]})
            continue
        best = max(s for s, _ in scored)
        picks = [o for s, o in scored if s == best]

        if best == 0:
            # không ràng buộc nào áp lên ô này → chỉ dám chọn khi có Nil (mặc định)
            nil = next((o for o in picks if o["code"].lower() in NIL), None)
            if nil is None:
                if len(opts) == 1:                 # ô literal, cố định
                    picks = opts
                elif not slot.get("is_required", True):
                    # ô tuỳ chọn không bị ràng buộc → bỏ qua, mã vẫn hợp lệ
                    continue
                else:
                    undecided.append({
                        "slot": slot["name"], "reason": "không có ràng buộc và không "
                        "có giá trị mặc định — cần người chọn",
                        "options": [f"{o['code']}={o['label']}" for o in opts][:8]})
                    continue
            else:
                picks = [nil]

        if len(picks) > 1:
            undecided.append({"slot": slot["name"], "reason": "nhiều option cùng thoả",
                              "options": [o["code"] for o in picks][:8]})
            continue

        o = picks[0]
        chosen[slot["name"]] = o["code"]
        if o["code"].lower() not in NIL:
            out += slot["separator"] + o["code"]

    return {"ok": not undecided, "part_number": out if not undecided else None,
            "series": row["code"], "chosen": chosen,
            "relaxed": relaxed or None,
            "undecided": undecided or None}
