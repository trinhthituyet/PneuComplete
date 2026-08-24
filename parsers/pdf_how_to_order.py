"""Parser sơ đồ How-to-Order trong PDF catalog → code_slot + code_option.

Đây là parser quan trọng nhất của cả hệ thống: nó sinh ra ngữ pháp mã hàng, tức
toàn bộ khả năng parse `CDM2L32-500Z`. Sai ở đây là sai mọi thứ phía sau.

Thuật toán 5 bước (docs/DESIGN.md §4.5), rút ra từ dữ liệu thật của PDF CM2:

  SPINE  dòng chứa mã mẫu — cho số ô, thứ tự ô, toạ độ x từng ô:
           y=186  CM2   B    40   150  A    Z
           y=210  CDM2  B    40   150  A    Z    M9BW
           x=     81    126  141  182  206  250  307
  CODE   token trông như mã option (Nil, B, TF, BZ, 40, M9BW…)
  LABEL  gom bằng CỬA SỔ 2D quanh mã: Δx ∈ (0, 70), |Δy| ≤ 4.
         Cần 2D vì label hay nằm ở DÒNG DƯỚI, thụt vào — dữ liệu thật:
           y=264  32:F   97:V   208:Rod 223:boot
           y=267         52:Rod 63:flange   106:Integrated 129:clevis 143:(90°)
         'F' ở y=264 nhưng label "Rod flange" ở y=267. Đọc theo dòng là sai.
  RUN    gom mã thành cột dọc: cùng x (±3), khoảng cách dòng liên tiếp ≤ 14.
         Ngưỡng 14 quan trọng: cùng dải x=173 chứa 2 ô khác nhau —
         port thread (y 237→249, Δy=6) và rod boot (y 270→285, Δy=9),
         cách nhau Δy=21 nên bị tách đúng.
  MERGE  ô mounting trải trên 2 cột con (x=32 và x=97) cùng dải y → gộp lại
         nếu Δx ≤ 70 và y chồng nhau. Port thread (x=173) cách 78 nên không gộp.
  MAP    mỗi token của SPINE khớp với RUN chứa đúng mã đó ⇒ biết RUN nào là ô nào.
         Ô có giá trị mặc định 'Nil' KHÔNG xuất hiện trong spine → chỉ ra được
         là ô, nhưng không biết vị trí ⇒ đẩy vào review_item.
"""
import re
import subprocess

NAME = "pdf_how_to_order"
VERSION = "3"   # v3: cụm x đúng cách, giới hạn vùng sơ đồ, đặt tên ô theo mã trước

# ── ngưỡng hình học, đơn vị point; rút ra từ PDF CM2 trang 6 ─────────────────
LABEL_DX = 70.0     # bề rộng cửa sổ tìm label bên phải mã
LABEL_DY = 4.0      # label lệch dòng tối đa
RUN_DX = 4.0        # cùng cột thì x lệch tối đa
RUN_GAP_DY = 14.0   # khoảng cách dòng liên tiếp trong cùng ô
MERGE_DX = 70.0     # 2 cột con của cùng một ô cách nhau tối đa
HEADER_DY = 13.0    # tiêu đề ô nằm ngay trên đỉnh run
# Vùng sơ đồ quanh spine. Ngoài vùng này là bảng "Applicable Auto Switches"
# (trên trang CM2 nằm ở y>420) — cấu trúc bảng, không phải sơ đồ, gom vào sẽ
# ra rác kiểu '24 VDC.', '0.5 m', '5 V,'.
DIAGRAM_UP = 200.0
DIAGRAM_DOWN = 150.0

_WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>'
)
# mã option: Nil, B, TF, BZ, M9BW, 40, 10A…
_CODE = re.compile(r"^(?:Nil|[A-Z][A-Z0-9]{0,5}|\d{1,4}(?:\.\d)?)$")
# loại nhầm: từ tiếng Anh viết hoa toàn phần, ký hiệu chú thích
_NOT_CODE = {"NPT", "RC", "PDF", "SMC", "OM", "AND", "OR", "TO", "FOR", "WITH",
             "NOTE", "MPA", "MM", "CE", "UL"}


def words(pdf_path, page: int):
    """Toạ độ từng word của 1 trang, qua pdftotext -bbox-layout (không cần lib ngoài)."""
    out = subprocess.run(
        ["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    return [(float(a), float(b), float(c), float(d), e)
            for a, b, c, d, e in _WORD.findall(out)]


def pages_with_hto(pdf_path):
    """Trang nào có sơ đồ How to Order (dùng text thường, nhanh)."""
    out = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                         capture_output=True, text=True, timeout=300).stdout
    return [i for i, pg in enumerate(out.split("\f"), 1)
            if re.search(r"how to order", pg, re.I)]


def _is_code(t: str) -> bool:
    return bool(_CODE.match(t)) and t.upper() not in _NOT_CODE


def find_spine(ws, series_hint: str | None = None):
    """Dòng mã mẫu: nhiều token ngắn, có token là mã series.

    Trả (series_token, [(x, token)…]) sắp theo x, hoặc (None, []).
    """
    rows = {}
    for x0, y0, _, _, t in ws:
        if t.strip():
            rows.setdefault(round(y0 / 2.0), []).append((x0, t.strip()))
    best = (None, [])
    for _, cells in sorted(rows.items()):
        cells = sorted(cells)
        toks = [t for _, t in cells]
        if not 3 <= len(toks) <= 12:
            continue
        if not all(_is_code(t) for t in toks):
            continue
        # Token đầu phải là mã series: bắt đầu bằng CHỮ, có thể kèm số.
        #
        # LỖI CŨ: `^[A-Z]{1,4}\d` bắt buộc kết thúc bằng CHỮ SỐ. Đúng cho CM2,
        # SY5, KQ2, SS5Y — nhưng loại thẳng AN, VQ, AS, MGP, AC (họ chỉ có chữ).
        # Đó là lý do 5 họ đó phải nhập tay YAML, và vì sao chạy `grammar` trên
        # AN/VQ/VT ra 0 slot dù trang How-to-Order đọc rõ "AN 20 C 10 02".
        head = toks[0]
        if len(head) < 2 or not re.match(r"^[A-Z]{2,5}\d{0,3}$", head, re.I):
            continue
        if series_hint:
            # SMC chèn 'D' sau chữ đầu để chỉ loại có nam châm: CM2 → CDM2.
            # Không chuẩn hoá thì dòng CDM2 (có thêm ô auto switch) bị loại,
            # và ta mất đúng cái ô cần nhất.
            norm = re.sub(r"^([A-Z])D", r"\1", head.upper())
            if not (head.upper().startswith(series_hint.upper()[:2])
                    or norm.startswith(series_hint.upper()[:2])):
                continue
        if len(toks) > len(best[1]):          # lấy dòng dài nhất: có auto switch
            best = (head, cells)
    return best


def collect(ws):
    """Gom (mã, label) bằng cửa sổ 2D, rồi dựng RUN dọc và gộp cột con."""
    codes = [(x0, y0, t.strip()) for x0, y0, _, _, t in ws if _is_code(t.strip())]
    code_pos = {(round(x), round(y)) for x, y, _ in codes}

    items = []
    for x, y, c in codes:
        label = [(wx, wt.strip()) for wx, wy, _, _, wt in ws
                 if wt.strip()
                 and 0 < wx - x <= LABEL_DX and abs(wy - y) <= LABEL_DY
                 and (round(wx), round(wy)) not in code_pos]
        items.append({"code": c, "x": x, "y": y,
                      "label": " ".join(t for _, t in sorted(label))})

    # Cụm x thành cột. KHÔNG dùng round(x/RUN_DX) làm khoá: x=31 và x=32 sẽ rơi
    # vào 2 bucket khác nhau và cắt đứt run — lỗi thật đã gặp, làm mất C/D/U
    # khỏi ô mounting. Phải cụm theo khoảng cách tới cột đang mở.
    items.sort(key=lambda i: i["x"])
    cols, cur_col = [], []
    for it in items:
        if cur_col and it["x"] - cur_col[0]["x"] <= RUN_DX:
            cur_col.append(it)
        else:
            if cur_col:
                cols.append(cur_col)
            cur_col = [it]
    if cur_col:
        cols.append(cur_col)

    # RUN: trong mỗi cột, cắt khi khoảng cách dòng > RUN_GAP_DY
    runs = []
    for col in cols:
        col.sort(key=lambda i: i["y"])
        cur = []
        for it in col:
            if cur and 0 < it["y"] - cur[-1]["y"] <= RUN_GAP_DY:
                cur.append(it)
            else:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = [it]
        if len(cur) >= 2:
            runs.append(cur)

    # MERGE: 2 cột con của cùng một ô (mounting) — gần nhau theo x, chồng nhau theo y
    merged, used = [], set()
    for i, a in enumerate(runs):
        if i in used:
            continue
        group = list(a)
        ay = (min(r["y"] for r in a), max(r["y"] for r in a))
        ax = a[0]["x"]
        for j, b in enumerate(runs):
            if j <= i or j in used:
                continue
            by = (min(r["y"] for r in b), max(r["y"] for r in b))
            if abs(b[0]["x"] - ax) <= MERGE_DX and \
               not (by[1] < ay[0] - 6 or by[0] > ay[1] + 6):
                group += b
                used.add(j)
        used.add(i)
        # dedupe theo mã, giữ label dài nhất
        best = {}
        for r in sorted(group, key=lambda r: (r["y"], r["x"])):
            if r["code"] not in best or len(r["label"]) > len(best[r["code"]]["label"]):
                best[r["code"]] = r
        merged.append(sorted(best.values(), key=lambda r: (r["y"], r["x"])))
    return merged


def header_of(ws, run):
    """Tiêu đề ô: các word ngay trên đỉnh run, trong dải x của run."""
    top = min(r["y"] for r in run)
    x0 = min(r["x"] for r in run) - 20
    x1 = max(r["x"] for r in run) + 120
    got = [(wx, wt.strip()) for wx, wy, _, _, wt in ws
           if wt.strip() and 0 < top - wy <= HEADER_DY and x0 <= wx <= x1]
    return " ".join(t for _, t in sorted(got))[:60]


# gợi ý tên ô từ nội dung label khi không có tiêu đề rõ
HINTS = [
    (r"foot|flange|clevis|trunnion|basic|boss", "mounting"),
    (r"cushion", "cushion"),
    (r"\bRc\b|NPT|thread", "port_thread"),
    (r"rod boot|tarpaulin", "rod_boot"),
    (r"auto switch|switch", "auto_switch"),
    (r"pneumatic|air-hydro", "fluid"),
    (r"knuckle|bracket", "rod_end_accessory"),
]


def name_slot(header: str, labels: list[str], codes: list[str]) -> str | None:
    """Đặt tên ô. Xét MÃ trước rồi mới tới chữ.

    Phải xét mã trước vì cửa sổ tiêu đề hay hút chữ của ô bên cạnh: ô bore
    (20/25/32/40) từng bị đặt tên 'cushion' chỉ vì tiêu đề lân cận có chữ
    'Air cushion'.
    """
    if codes and all(re.fullmatch(r"\d{1,3}", c) for c in codes):
        vals = sorted(int(c) for c in codes)
        # bore của SMC nằm trong 2.5..200 và là tập rời rạc nhỏ
        if len(vals) <= 20 and vals[0] >= 2 and vals[-1] <= 320:
            return "bore"
        return "numeric"
    blob = (header + " " + " ".join(labels)).lower()
    for pat, name in HINTS:
        if re.search(pat, blob, re.I):
            return name
    return None


def parse(pdf_path, page: int, series_hint=None):
    ws = words(pdf_path, page)
    series_tok, spine = find_spine(ws, series_hint)

    # chỉ giữ vùng sơ đồ quanh spine; ngoài đó là bảng auto switch → rác
    if spine:
        sy = next(y for x0, y, _, _, t in ws
                  if abs(x0 - spine[0][0]) < 1 and t.strip() == spine[0][1])
        ws_diagram = [w for w in ws if sy - DIAGRAM_UP <= w[1] <= sy + DIAGRAM_DOWN]
    else:
        ws_diagram = ws
    runs = collect(ws_diagram)

    out = {"page": page, "series_token": series_tok,
           "spine": [{"x": x, "token": t} for x, t in spine],
           "slots": [], "unmapped": []}

    spine_toks = [t for _, t in spine][1:] if spine else []   # bỏ mã series
    taken = set()
    for pos, tok in enumerate(spine_toks, start=1):
        hit = None
        for ri, run in enumerate(runs):
            if ri in taken:
                continue
            if any(r["code"] == tok for r in run):
                hit = (ri, run)
                break
        if hit is None:
            # không thuộc enum nào → ô kiểu số (stroke) hoặc mã bảng riêng
            if tok.isdigit():
                nm, vt, cf = "stroke", "integer", 0.8
            elif re.match(r"^[A-Z]\d[A-Z]{1,4}$", tok):
                # 'M9BW' — mã auto switch, bảng riêng ngoài vùng sơ đồ
                nm, vt, cf = "auto_switch", "free", 0.7
            elif len(tok) <= 2:
                # 'Z' — hậu tố cố định của series, không phải ô người dùng chọn
                nm, vt, cf = "series_suffix", "literal", 0.75
            else:
                nm, vt, cf = None, "free", 0.5
            out["slots"].append({
                "pos": pos, "sample": tok, "name": nm,
                "value_type": vt, "options": [], "confidence": cf,
            })
            continue
        ri, run = hit
        taken.add(ri)
        header = header_of(ws_diagram, run)
        codes = [r["code"] for r in run]
        out["slots"].append({
            "pos": pos, "sample": tok,
            "name": name_slot(header, [r["label"] for r in run], codes),
            "header": header, "value_type": "enum",
            "options": [{"code": r["code"], "label": r["label"]} for r in run],
            "confidence": 0.85,
        })

    for ri, run in enumerate(runs):
        if ri in taken or len(run) < 2:
            continue
        header = header_of(ws_diagram, run)
        codes = [r["code"] for r in run]
        out["unmapped"].append({
            "name": name_slot(header, [r["label"] for r in run], codes),
            "header": header,
            "options": [{"code": r["code"], "label": r["label"]} for r in run],
        })
    return out


def load(con, run_id, data, series_id, source_id=None, source_page=None):
    """Ghi code_slot + code_option cho ô đã khớp spine; ô chưa khớp → review_item.

    Chỉ ô nào khớp spine VÀ đặt được tên mới ghi thẳng. Ô 'unmapped' vẫn là dữ
    liệu đúng (Nil/Rc/NPT…) nhưng chưa biết vị trí trong mã ⇒ người duyệt gán.
    """
    from crawler import db as _db

    # Ngữ pháp NHẬP TAY đã được người đọc catalog xác nhận — parser máy KHÔNG
    # được ghi đè. Lỗi thật đã gặp: chạy lại `crawler.run grammar` đè ô 'bore'
    # (32 option màu ống hiểu sai thành bore) lên ngữ pháp TU nhập tay, làm
    # engine/parser.py vỡ: "could not convert string to float: 'BU'".
    src = con.execute("select grammar_source from series where id=?",
                      (series_id,)).fetchone()
    if src and src["grammar_source"] == "manual":
        return {"slots": 0, "options": 0, "reviews": 0,
                "skipped": "ngữ pháp nhập tay — không ghi đè"}

    # part_prefix: mã series lấy từ SPINE của chính sơ đồ ('CDM2' trong
    # 'CDM2 B 40 150 A Z M9BW'). Không ghi thì engine/parser.py phải suy từ
    # series.code — sinh ra tiền tố sai với code dạng nhóm ('CM2/CDM2-Z').
    if data.get("series_token"):
        con.execute("""update series set part_prefix=coalesce(part_prefix,?),
                       grammar_source=coalesce(grammar_source,'auto') where id=?""",
                    (data["series_token"].upper(), series_id))

    n_slot = n_opt = n_review = 0
    for s in data["slots"]:
        gate = s["confidence"] >= 0.8 or s["value_type"] != "enum"
        if not s["name"] or not gate:
            _db.add_review(con, run_id, "code_slot",
                           {"series_id": series_id, **s, "source_page": source_page},
                           confidence=s["confidence"],
                           note="ô khớp spine nhưng chưa đặt được tên")
            n_review += 1
            continue
        # 'literal' không nằm trong check constraint của code_slot, mà bản chất
        # nó là enum có đúng 1 giá trị → ghi thành enum. insert or ignore sẽ bỏ
        # qua âm thầm nếu vi phạm constraint, nên phải quy đổi ở đây.
        vt = "enum" if s["value_type"] == "literal" else s["value_type"]
        con.execute(
            """insert into code_slot
               (series_id, pos, name, value_type, separator) values (?,?,?,?,?)
               on conflict (series_id, pos) do update set
                 name=excluded.name, value_type=excluded.value_type""",
            (series_id, s["pos"], s["name"], vt,
             "-" if s["name"] == "stroke" else ""),
        )
        slot = con.execute("select id from code_slot where series_id=? and pos=?",
                           (series_id, s["pos"])).fetchone()
        n_slot += 1
        opts = s["options"]
        if s["value_type"] == "literal" and not opts:
            opts = [{"code": s["sample"], "label": "giá trị cố định của series"}]
        for o in opts:
            attrs = {}
            if s["name"] == "bore" and o["code"].isdigit():
                attrs["bore_mm"] = float(o["code"])
            cur = con.execute(
                """insert or ignore into code_option (slot_id, code, label, attrs)
                   values (?,?,?,?)""",
                (slot["id"], o["code"], o["label"] or None,
                 __import__("json").dumps(attrs)),
            )
            n_opt += cur.rowcount

    for u in data["unmapped"]:
        _db.add_review(con, run_id, "code_option",
                       {"series_id": series_id, "slot_hint": u["name"],
                        "header": u["header"], "options": u["options"],
                        "source_page": source_page},
                       confidence=0.6,
                       note="ô đọc được từ sơ đồ nhưng không khớp token nào của "
                            "spine (thường vì giá trị mặc định là Nil, bị lược "
                            "khỏi mã mẫu) — cần người gán vị trí ô")
        n_review += 1

    con.commit()
    return {"slots": n_slot, "options": n_opt, "reviews": n_review}
